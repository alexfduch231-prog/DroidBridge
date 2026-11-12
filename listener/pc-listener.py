#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервер локального управления для приложения ВзаимоПульт.

Работает на домашнем ПК, ждёт HTTP-запросы в локальной сети и запускает штатное
выключение Windows. Никаких agent-привилегий не требует: обычный запуск от имени
твоего пользователя (через папку Автозагрузка), чтобы имелось право Shutdown.

Эндпоинты (все требуют ?key=<токен>):
    /ping     -> "ok"                       проверка, что слушатель жив
    /off      -> shutdown /s /t <delay>     выключение с окном на отмену
    /restart  -> shutdown /r /t <delay>     перезагрузка с окном на отмену
    /lock     -> LockWorkStation            блокировка экрана
    /screen   -> монитор в ждущий режим     экран гаснет, ПК продолжает работать
    /cancel   -> shutdown /a               отмена уже назначенной команды
    /app?id=… -> запуск приложения из белого списка apps.json
    /away     -> блокировка + монитор погашен, «ушёл из дома»
    /media?action=… -> медиа-клавиши: playpause, next, prev, volup, voldown, mute
    /timer?min=… -> выключение через N минут (отмена тем же /cancel)
    /status   -> JSON: cpu, ram, uptime, gpu (только чтение)
    /shot?q=60&w=1280 -> JPEG-кадр экрана (только чтение, для просмотра)
    /stream?w=1080&fps=60 -> аппаратный H.264-поток экрана для телефона
    /type?text=…&enter=1 -> набрать текст в активное окно (Unicode, SendInput)
    /key?name=backspace|enter|tab|escape -> одна клавиша
    /mirror?port=8768 -> открыть на ПК окно с экраном и звуком телефона

Токен лежит рядом в token.txt и генерируется автоматически при первом запуске.
В чат/логи он не печатается нигде (только маска).
"""

import argparse
import ctypes
import ctypes.wintypes as wintypes
import hmac
import http.server
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
# The deployed embedded Python uses an isolated ._pth without the script directory.
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from file_upload import handle_upload
DATA_DIR = os.path.abspath(os.environ.get("VZAIMOPULT_DATA_DIR") or HERE)
os.makedirs(DATA_DIR, exist_ok=True)
TOKEN_FILE = os.path.join(DATA_DIR, "token.txt")
APPS_FILE = os.path.join(DATA_DIR, "apps.json")
LOG_FILE = os.path.join(DATA_DIR, "listener.log")

CLIENT_DIR = os.path.join(os.path.dirname(HERE), "client")
CLIENT_SCRIPT = os.path.join(CLIENT_DIR, "pc-viewer.pyw")
CLIENT_PID = os.path.join(CLIENT_DIR, "client.pid")
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
CLIENT_PYTHONW = os.path.join(LOCAL_APPDATA, "Python", "bin", "pythonw.exe")
FFMPEG_FALLBACK = os.path.join(LOCAL_APPDATA, "Microsoft", "WinGet", "Links", "ffmpeg.exe")

DETACHED_FLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
CREATE_NO_WINDOW = 0x08000000

# Виртуальные клавиши Windows: работают с любым плеером, без сторонних утилит.
MEDIA_KEYS = {
    "playpause": (0xB3, "плей/пауза"),
    "next": (0xB0, "следующий трек"),
    "prev": (0xB1, "предыдущий трек"),
    "volup": (0xAF, "громче"),
    "voldown": (0xAE, "тише"),
    "mute": (0xAD, "звук переключён"),
}
KEYEVENTF_KEYUP = 0x0002

STARTED_AT = time.time()

_get_tick_count64 = ctypes.windll.kernel32.GetTickCount64
_get_tick_count64.restype = ctypes.c_ulonglong


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _sys_times():
    idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    def val(ft):
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return val(idle), val(kern), val(user)


def system_status():
    """CPU/RAM/uptime без внешних пакетов: только WinAPI."""
    info = {"ok": True}
    try:
        info["uptime_s"] = int(_get_tick_count64() / 1000)
    except Exception:
        pass
    try:
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            info["ram"] = int(mem.dwMemoryLoad)
            info["mem_total_mb"] = int(mem.ullTotalPhys // (1024 * 1024))
            info["mem_free_mb"] = int(mem.ullAvailPhys // (1024 * 1024))
    except Exception:
        pass
    try:
        i1, k1, u1 = _sys_times()
        time.sleep(0.2)
        i2, k2, u2 = _sys_times()
        total = (k2 - k1) + (u2 - u1)
        idle = i2 - i1
        if total > 0:
            info["cpu"] = max(0, min(100, int(round(100.0 * (1.0 - idle / float(total))))))
    except Exception:
        pass
    info["gpu"] = gpu_status()
    return info


def gpu_status():
    """Видеокарта NVIDIA через nvidia-smi. Нет утилиты или карты - None."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
            creationflags=0x08000000).stdout
        line = out.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            return None
        return {
            "name": parts[0],
            "util": int(float(parts[1])),
            "mem_used_mb": int(float(parts[2])),
            "mem_total_mb": int(float(parts[3])),
            "temp": int(round(float(parts[4]))),
        }
    except Exception:
        return None


_screen_lock = threading.Lock()

KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_TAB = 0x09
VK_ESCAPE = 0x1B
SINGLE_KEYS = {"enter": VK_RETURN, "backspace": VK_BACK, "tab": VK_TAB, "escape": VK_ESCAPE}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUTUNION)]


def _key_input(vk, scan, flags):
    inp = INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = scan
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = 0
    return inp


def _send_input(items):
    array = (INPUT * len(items))(*items)
    sent = ctypes.windll.user32.SendInput(len(items), array, ctypes.sizeof(INPUT))
    if sent != len(items):
        raise OSError("SendInput принял %d из %d" % (sent, len(items)))


def type_text(text):
    """Unicode-ввод в активное окно, без буфера обмена; \\n -> Enter."""
    data = text.encode("utf-16-le")
    items = []
    for i in range(0, len(data), 2):
        code = int.from_bytes(data[i:i + 2], "little")
        if code in (0x0A, 0x0D):
            items.append(_key_input(VK_RETURN, 0, 0))
            items.append(_key_input(VK_RETURN, 0, 0x0002))
        else:
            items.append(_key_input(0, code, KEYEVENTF_UNICODE))
            items.append(_key_input(0, code, KEYEVENTF_UNICODE | 0x0002))
    if items:
        _send_input(items)


def press_key(name):
    vk = SINGLE_KEYS[name]
    _send_input([_key_input(vk, 0, 0), _key_input(vk, 0, 0x0002)])


def screen_jpeg(max_width=1280, quality=60, fast=False):
    """Кадр экрана в JPEG через Pillow. Только чтение, без внешних утилит."""
    from PIL import Image, ImageGrab
    with _screen_lock:
        img = ImageGrab.grab()
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max_width and img.width > max_width:
            height = int(round(img.height * max_width / float(img.width)))
            method = Image.BILINEAR if fast else Image.LANCZOS
            img = img.resize((max_width, height), method)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


def send_media_key(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def mask(secret):
    """Токен наружу не показываем: только длина и первые два символа."""
    if not secret:
        return "(пусто)"
    return secret[:2] + "*" * max(0, len(secret) - 2)


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = "[%s] %s\n" % (stamp, line)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def load_token(create=True):
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    if not create:
        return ""
    tok = secrets.token_urlsafe(16)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    log("token.txt создан, токен = %s (%d знаков). Открой файл и впиши его в приложение."
        % (mask(tok), len(tok)))
    return tok


def run_cmd(args):
    """Запуск команды Windows без окна. Возвращает (rc, текст_ошибки)."""
    try:
        p = subprocess.run(args, capture_output=True)
    except Exception as e:
        return 1, repr(e)
    out = b""
    if p.stderr:
        out = p.stderr
    elif p.stdout:
        out = p.stdout
    # Вывод системных утилит в OEM-кодировке (cp866/cp1251), читаем с заменой мусора.
    text = ""
    for enc in ("cp866", "cp1251", "utf-8"):
        try:
            text = out.decode(enc, errors="replace").strip()
            break
        except Exception:
            continue
    return p.returncode, text


def load_apps():
    """Белый список приложений. Читается заново на каждый запрос: править можно без рестарта."""
    try:
        from app_catalog import load_catalog
        data = load_catalog(APPS_FILE)
    except (ValueError, OSError):
        return {}, "Список программ недоступен"
    apps = {}
    for item in data.get("apps") or []:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id", "")).strip().lower()
        if aid and item.get("path"):
            apps[aid] = item
    return apps, ""


def client_alive():
    """Открыт ли уже клиент просмотра телефона (pid из client.pid)."""
    try:
        with open(CLIENT_PID, "r", encoding="ascii") as f:
            pid = int(f.read().strip())
    except Exception:
        return False
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def start_mirror_client(ip, port):
    """Открывает окно клиента; он сам подключится к TCP-серверу телефона."""
    if not os.path.isfile(CLIENT_SCRIPT):
        return False, "клиент не найден: %s" % CLIENT_SCRIPT
    if not os.path.isfile(CLIENT_PYTHONW):
        return False, "pythonw.exe не найден: %s" % CLIENT_PYTHONW
    try:
        subprocess.Popen(
            [CLIENT_PYTHONW, CLIENT_SCRIPT, "--connect", ip, "--port", str(port)],
            cwd=CLIENT_DIR, close_fds=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=DETACHED_FLAGS)
        return True, ""
    except Exception as e:
        return False, repr(e)


def launch_app(item):
    """Запуск строго по пути из apps.json. Возвращает (ok, текст)."""
    path = os.path.expandvars(str(item.get("path", "")))
    name = str(item.get("name") or item.get("id") or "приложение")
    if not os.path.isfile(path):
        return False, "файл не найден: %s" % path
    if os.path.splitext(path)[1].lower() == ".lnk":
        try:
            os.startfile(path)
            return True, name
        except OSError:
            return False, "Не удалось открыть ярлык"
    task = item.get("task")
    if task:
        # exe с манифестом requireAdministrator: обычный запуск даст ошибку 740,
        # поэтому стартуем заранее созданную задачу с уровнем «Наивысшие права».
        rc, err = run_cmd(["schtasks", "/run", "/tn", task])
        if rc == 0:
            return True, name
        log("задача %s не запустилась (rc=%d %s), пробую напрямую" % (task, rc, err))
    args = [str(a) for a in (item.get("args") or [])]
    cwd = item.get("cwd") or os.path.dirname(path)
    try:
        subprocess.Popen([path] + args, cwd=cwd, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=DETACHED_FLAGS)
        return True, name
    except OSError as e:
        if getattr(e, "winerror", None) == 740:
            return False, "%s требует прав администратора" % name
        return False, repr(e)
    except Exception as e:
        return False, repr(e)


def close_app(item):
    """Закрытие только тех процессов, что перечислены в apps.json ("process")."""
    procs = [str(p) for p in (item.get("process") or [])]
    name = str(item.get("name") or item.get("id") or "приложение")
    if not procs:
        return False, "для %s не задан процесс, закрыть можно только вручную" % name
    results = []
    ok_any = False
    for proc in procs:
        rc, err = run_cmd(["taskkill", "/IM", proc, "/F"])
        low = (err or "").lower()
        if rc == 0:
            ok_any = True
            results.append("%s закрыт" % proc)
        elif "не найден" in low or "not found" in low or "не запущен" in low:
            ok_any = True
            results.append("%s уже не запущен" % proc)
        else:
            results.append("%s: %s" % (proc, err or ("rc=%d" % rc)))
    return ok_any, "; ".join(results)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PcListener/1.0"

    # ---------- служебное ----------

    def send(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def send_bytes(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def authed(self, query):
        got = query.get("key", [""])[0]
        want = self.server.token
        if not want:
            return False
        return hmac.compare_digest(got.encode("utf-8"), want.encode("utf-8"))

    def client(self):
        try:
            return self.client_address[0]
        except Exception:
            return "?"

    def do_POST(self):
        if urlparse(self.path).path == '/input':
            from remote_input import handle_input
            handle_input(self)
        else:
            handle_upload(self)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            cmd = parsed.path.strip("/").lower()
            who = self.client()

            if cmd == "":
                self.send(200, "PcListener. Нужен /ping, /off, /restart, /lock, /screen, "
                               "/shot, /stream, /type, /key, /cancel, /away, /media, /timer, /status "
                               "или /app?id=... с ?key=...")
                return

            if not self.authed(query):
                log("ОТКАЗ: %s запросил /%s без правильного ключа" % (who, cmd))
                self.send(403, "ключ не подошёл")
                return

            if cmd == "ping":
                up = int(time.time() - STARTED_AT)
                self.send(200, "ok up=%ds delay=%ds dry=%s" % (up, self.server.delay,
                                                               self.server.dry_run))
                return

            if cmd in ("off", "restart"):
                flag = "/s" if cmd == "off" else "/r"
                name = "выключение" if cmd == "off" else "перезагрузка"
                action = "выключить" if cmd == "off" else "перезагрузить"
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил %s. Команда не запускалась." % (who, action))
                    self.send(200, "dry-run: shutdown %s /t %d НЕ выполнен"
                             % (flag, self.server.delay))
                    return
                rc, err = run_cmd(["shutdown", flag, "/t", str(self.server.delay)])
                if rc == 0:
                    log("%s: %s, окно на отмену %d с" % (name.upper(), who, self.server.delay))
                    self.send(200, "%s через %d с, можно отменить" % (name, self.server.delay))
                else:
                    log("ОШИБКА (%s): rc=%d %s" % (name, rc, err))
                    self.send(500, "не удалось: %s" % (err or ("rc=%d" % rc)))
                return

            if cmd == "lock":
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил блокировку. Команда не запускалась." % who)
                    self.send(200, "dry-run: блокировка НЕ выполнена")
                    return
                try:
                    ok = bool(ctypes.windll.user32.LockWorkStation())
                    err = "" if ok else "LockWorkStation вернул 0"
                except Exception as e:
                    ok, err = False, repr(e)
                if ok:
                    log("БЛОКИРОВКА: %s" % who)
                    self.send(200, "экран заблокирован")
                else:
                    log("ОШИБКА блокировки: %s" % err)
                    self.send(500, "не удалось заблокировать: %s" % err)
                return

            if cmd == "screen":
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил погасить экран. Команда не запускалась." % who)
                    self.send(200, "dry-run: экран НЕ погашен")
                    return
                # WM_SYSCOMMAND/SC_MONITORPOWER=2 на широковещательное окно: монитор в ждущий режим,
                # сам ПК не спит. Возврат любого ввода включает экран обратно.
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                    ok, err = True, ""
                except Exception as e:
                    ok, err = False, repr(e)
                if ok:
                    log("ЭКРАН ВЫКЛ: %s" % who)
                    self.send(200, "экран погашен")
                else:
                    log("ОШИБКА гашения экрана: %s" % err)
                    self.send(500, "не удалось погасить экран: %s" % err)
                return

            if cmd == "cancel":
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил отменить. shutdown /a не запускался." % who)
                    self.send(200, "dry-run: отмена не выполнялась")
                    return
                rc, err = run_cmd(["shutdown", "/a"])
                if rc == 0:
                    log("ОТМЕНА: %s отменил команду" % who)
                    self.send(200, "команда отменена")
                else:
                    log("ОТМЕНА не сработала: rc=%d %s" % (rc, err))
                    self.send(400, "отменять нечего: %s" % (err or ("rc=%d" % rc)))
                return

            if cmd == "apps":
                from app_catalog import public_catalog, CatalogError
                try:
                    payload = {"ok": True, "apps": public_catalog(APPS_FILE)}
                    status = 200
                except (CatalogError, OSError):
                    payload = {"ok": False, "error": "Application list unavailable"}
                    status = 503
                self.send_bytes(status, "application/json; charset=utf-8",
                                json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return

            if cmd == "app":
                app_id = (query.get("id") or [""])[0].strip()
                if not app_id:
                    self.send(400, "нужен параметр id")
                    return
                apps, err = load_apps()
                item = apps.get(app_id.lower())
                if not item:
                    log("ЗАПУСК: %s попросил неизвестное приложение %r" % (who, app_id))
                    self.send(404, "нет такого приложения в списке: %s" % app_id)
                    return
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил запустить %s. Не запускалось." % (who, item.get("name")))
                    self.send(200, "dry-run: %s НЕ запущен" % item.get("name"))
                    return
                action = (query.get("action") or [""])[0].strip().lower()
                if action == "close":
                    ok, text = close_app(item)
                    if ok:
                        log("ЗАКРЫТИЕ: %s -> %s (%s)" % (who, item.get("name"), text))
                        self.send(200, "закрываю %s: %s" % (item.get("name"), text))
                    else:
                        log("ОШИБКА закрытия %s: %s" % (app_id, text))
                        self.send(500, "не удалось закрыть %s: %s" % (app_id, text))
                    return
                ok, text = launch_app(item)
                if ok:
                    log("ЗАПУСК: %s -> %s (%s)" % (who, item.get("name"), text))
                    self.send(200, "запускаю %s" % item.get("name"))
                else:
                    log("ОШИБКА запуска %s: %s" % (app_id, text))
                    self.send(500, "не удалось запустить %s: %s" % (app_id, text))
                return

            if cmd == "away":
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил «ушёл из дома». Ничего не выполнялось." % who)
                    self.send(200, "dry-run: блокировка и гашение экрана НЕ выполнены")
                    return
                try:
                    locked = bool(ctypes.windll.user32.LockWorkStation())
                except Exception as e:
                    locked = False
                    log("ОШИБКА блокировки: %r" % (e,))
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                    screen_ok = True
                except Exception:
                    screen_ok = False
                log("УШЁЛ ИЗ ДОМА: %s (lock=%s screen=%s)" % (who, locked, screen_ok))
                if locked:
                    self.send(200, "экран заблокирован, монитор погашен")
                else:
                    self.send(500, "не удалось заблокировать экран")
                return

            if cmd == "media":
                action = (query.get("action") or [""])[0].strip().lower()
                entry = MEDIA_KEYS.get(action)
                if not entry:
                    self.send(400, "неизвестное действие: %s" % action)
                    return
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил медиа «%s». Не отправлялось." % (who, entry[1]))
                    self.send(200, "dry-run: %s НЕ отправлено" % entry[1])
                    return
                try:
                    send_media_key(entry[0])
                    log("МЕДИА: %s -> %s" % (who, entry[1]))
                    self.send(200, entry[1])
                except Exception as e:
                    log("ОШИБКА медиа: %r" % (e,))
                    self.send(500, "не удалось: %r" % (e,))
                return

            if cmd == "timer":
                raw = (query.get("min") or [""])[0].strip()
                try:
                    minutes = int(raw)
                except ValueError:
                    minutes = 0
                if minutes < 1 or minutes > 1440:
                    self.send(400, "нужно min от 1 до 1440")
                    return
                sec = minutes * 60
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил таймер на %d мин. shutdown не запускался."
                        % (who, minutes))
                    self.send(200, "dry-run: таймер на %d мин НЕ поставлен" % minutes)
                    return
                rc, err = run_cmd(["shutdown", "/s", "/t", str(sec)])
                if rc == 0:
                    log("ТАЙМЕР: %s поставил выключение через %d мин" % (who, minutes))
                    self.send(200, "выключение через %d мин, отмена — «Отменить команду»" % minutes)
                else:
                    log("ОШИБКА таймера: rc=%d %s" % (rc, err))
                    self.send(500, "не удалось: %s" % (err or ("rc=%d" % rc)))
                return

            if cmd == "status":
                body = json.dumps(system_status(), ensure_ascii=False)
                self.send(200, body)
                return

            if cmd == "shot":
                try:
                    width = max(320, min(2560, int((query.get("w") or ["1280"])[0])))
                except ValueError:
                    width = 1280
                try:
                    quality = max(20, min(90, int((query.get("q") or ["60"])[0])))
                except ValueError:
                    quality = 60
                try:
                    data = screen_jpeg(width, quality)
                except Exception as e:
                    log("ОШИБКА кадра: %r" % (e,))
                    self.send(500, "не удалось снять экран: %r" % (e,))
                    return
                self.send_bytes(200, "image/jpeg", data)
                return

            if cmd == "stream":
                try:
                    width = max(320, min(2560, int((query.get("w") or ["1080"])[0])))
                except ValueError:
                    width = 1080
                try:
                    fps = max(5, min(60, int((query.get("fps") or ["60"])[0])))
                except ValueError:
                    fps = 60
                try:
                    user32 = ctypes.windll.user32
                    screen_w = int(user32.GetSystemMetrics(0)) or 1920
                    screen_h = int(user32.GetSystemMetrics(1)) or 1080
                except Exception:
                    screen_w, screen_h = 1920, 1080
                if width > screen_w:
                    width = screen_w
                height = int(round(screen_h * width / float(screen_w) / 2.0)) * 2

                ffmpeg = shutil.which("ffmpeg") or FFMPEG_FALLBACK
                if not os.path.isfile(ffmpeg):
                    self.send(500, "нет ffmpeg")
                    return
                cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
                       "-f", "lavfi", "-i", "ddagrab=0:framerate=%d" % fps,
                       "-vf", "hwdownload,format=bgra,scale=%d:%d:flags=fast_bilinear"
                              % (width, height),
                       "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
                       "-rc", "cbr", "-b:v", "6M", "-maxrate", "6M", "-bufsize", "3M",
                       "-g", str(fps), "-bf", "0",
                       "-bsf:v", "h264_metadata=aud=insert",
                       "-f", "h264", "pipe:1"]
                self.send_response(200)
                self.send_header("Content-Type", "video/h264")
                self.send_header("X-Video-Width", str(width))
                self.send_header("X-Video-Height", str(height))
                self.send_header("X-Video-Fps", str(fps))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                log("ПОТОК: %s смотрит экран ПК (H.264 %dx%d @%d)"
                    % (who, width, height, fps))
                proc = None
                total = 0
                try:
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                            creationflags=CREATE_NO_WINDOW)
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        total += len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                except Exception as e:
                    log("ОШИБКА потока %s: %r" % (who, e))
                finally:
                    if proc is not None:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        try:
                            err = proc.stderr.read().decode("utf-8", "replace")
                        except Exception:
                            err = ""
                        if err.strip():
                            log("ПОТОК ffmpeg: %s" % err.strip()[:300])
                    log("ПОТОК: %s закрыл экран ПК (%.1f КБ)"
                        % (who, total / 1024.0))
                return

            if cmd == "mirror":
                try:
                    port = int((query.get("port") or ["8768"])[0])
                except ValueError:
                    port = 8768
                if port < 1024 or port > 65535:
                    self.send(400, "плохой порт")
                    return
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил трансляцию экрана телефона на ПК (порт %d). "
                        "Клиент не запускался." % (who, port))
                    self.send(200, "dry-run: клиент не запущен")
                    return
                if client_alive():
                    self.send(200, "клиент уже открыт")
                    return
                ok, err = start_mirror_client(self.client_address[0], port)
                if ok:
                    log("ТРАНСЛЯЦИЯ: открыл клиент для %s, порт %d"
                        % (self.client_address[0], port))
                    self.send(200, "клиент открыт")
                else:
                    log("ОШИБКА трансляции: %s" % err)
                    self.send(500, "клиент не открылся: %s" % err)
                return

            if cmd == "type":
                text = (query.get("text") or [""])[0]
                enter = (query.get("enter") or ["0"])[0].lower() in ("1", "true", "yes")
                if len(text) > 1000:
                    self.send(400, "слишком длинный текст (максимум 1000 знаков)")
                    return
                if not text.strip() and not enter:
                    self.send(400, "пустой текст")
                    return
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил ввод %d знаков%s. Не набиралось."
                        % (who, len(text), " + Enter" if enter else ""))
                    self.send(200, "dry-run: текст не набран")
                    return
                try:
                    type_text(text)
                    if enter:
                        press_key("enter")
                    log("ВВОД: %s набрал %d знаков%s"
                        % (who, len(text), " + Enter" if enter else ""))
                    self.send(200, "набрано %d знаков%s"
                             % (len(text), " + Enter" if enter else ""))
                except Exception as e:
                    log("ОШИБКА ввода: %r" % (e,))
                    self.send(500, "не удалось набрать: %r" % (e,))
                return

            if cmd == "key":
                name = (query.get("name") or [""])[0].strip().lower()
                if name not in SINGLE_KEYS:
                    self.send(400, "можно: " + ", ".join(sorted(SINGLE_KEYS)))
                    return
                if self.server.dry_run:
                    log("DRY-RUN: %s попросил клавишу %s. Не нажималось." % (who, name))
                    self.send(200, "dry-run: клавиша не нажата")
                    return
                try:
                    press_key(name)
                    log("КЛАВИША: %s -> %s" % (who, name))
                    self.send(200, "нажато: %s" % name)
                except Exception as e:
                    log("ОШИБКА клавиши: %r" % (e,))
                    self.send(500, "не удалось: %r" % (e,))
                return

            self.send(404, "неизвестная команда: %s" % cmd)
        except Exception as e:
            log("СБОЙ обработки: %r" % (e,))
            try:
                self.send(500, "внутренняя ошибка")
            except Exception:
                pass

    def log_message(self, fmt, *args):
        # стандартный лог в stderr глушим, у нас свой
        pass


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description="HTTP-слушатель для выключения ПК с телефона")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = со всей локальной сети")
    ap.add_argument("--delay", type=int, default=20, help="секунд на отмену выключения")
    ap.add_argument("--dry-run", action="store_true",
                    help="не выключать, только писать в лог (для проверки)")
    ap.add_argument("--print-path", action="store_true", help="показать путь к токену и выйти")
    args = ap.parse_args()

    if args.print_path:
        print(TOKEN_FILE)
        return 0

    # Без DPI-awareness скриншот берётся в масштабе системы (размыто).
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    token = load_token()
    srv = Server((args.host, args.port), Handler)
    srv.token = token
    srv.upload_data_dir = DATA_DIR
    srv.delay = args.delay
    srv.dry_run = args.dry_run
    from remote_input import dispatch
    srv.input_backend = lambda event: dispatch(event, _send_input, INPUT, KEYBDINPUT, MOUSEINPUT, type_text)

    log("старт: http://%s:%d  delay=%ds  dry-run=%s  ключ=%s"
        % (args.host, args.port, args.delay, args.dry_run, mask(token)))
    log("файл с ключом: %s" % TOKEN_FILE)
    from lan_discovery import DiscoveryServer
    discovery = None
    discovery_thread = None
    try:
        discovery = DiscoveryServer(token, args.port, host=args.host)
        discovery_thread = threading.Thread(target=discovery.serve_forever, name="lan-discovery", daemon=True)
        discovery_thread.start()
        log("LAN discovery: UDP 8766, authenticated")
    except (OSError, ValueError):
        log("LAN discovery unavailable; HTTP listener continues")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("остановка по Ctrl+C")
    finally:
        if discovery is not None:
            discovery.close()
        if discovery_thread is not None:
            discovery_thread.join(timeout=1)
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
