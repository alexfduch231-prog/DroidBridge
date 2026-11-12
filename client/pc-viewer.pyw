#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПК-клиент «Экран телефона»: окно с картинкой и звуком телефона.

Телефон поднимает TCP-сервер, клиент подключается к нему сам: исходящее
соединение не требует новых правил файрвола (входящий разрешён только на 8765).
Протокол: [длина: 4 байта BE][тип: 1 байт][данные]
    0 - JSON с параметрами потока и токеном (клиент сверяет токен)
    1 - JPEG-кадр
    2 - PCM 16 бит little-endian
Звук играет ffplay, которому PCM отдаётся в stdin.
"""

import argparse
import array
import hmac
import io
import json
import os
import queue
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk
from control_geometry import image_point, gesture_command, encode_control, control_allowed

TYPE_HELLO = 0
TYPE_JPEG = 1
TYPE_PCM = 2
TYPE_H264 = 3
TYPE_H264_CONFIG = 4
TYPE_CONTROL = 5

MAX_PACKET = 8 * 1024 * 1024
CREATE_NO_WINDOW = 0x08000000

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("VZAIMOPULT_DATA_DIR") or HERE)
os.makedirs(DATA_DIR, exist_ok=True)
LOG_PATH = os.path.join(DATA_DIR, "client.log")
PID_PATH = os.path.join(DATA_DIR, "client.pid")
DEFAULT_TOKEN = (os.path.join(DATA_DIR, "token.txt") if os.environ.get("VZAIMOPULT_DATA_DIR")
                 else os.path.join(HERE, "..", "listener", "token.txt"))
_LISTENER_DIR = os.path.join(os.path.dirname(HERE), "listener")
if _LISTENER_DIR not in sys.path:
    sys.path.insert(0, _LISTENER_DIR)
from media_tools import MediaTools, MediaToolsError, resolve_media_tools
# Standalone viewer keeps its legacy token/data location; media settings are shared.
_MEDIA_DATA_DIR = DATA_DIR if os.environ.get("VZAIMOPULT_DATA_DIR") else _LISTENER_DIR
try:
    MEDIA_TOOLS = resolve_media_tools(_MEDIA_DATA_DIR)
except MediaToolsError:
    MEDIA_TOOLS = MediaTools(None, None, "invalid")

# Share desktop tokens when run directly as well as through the launcher.
_PROJECT_DIR = os.path.dirname(HERE)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)
from desktop.theme import PALETTE, apply_theme

BG = PALETTE["background"]
PANEL = PALETTE["surface"]
TEXT = PALETTE["text"]
MUTED = PALETTE["muted"]
PRIMARY = PALETTE["primary"]
OK = "#187645"
BAD = PALETTE["danger"]


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def read_token(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read().strip()


def write_pid():
    try:
        with open(PID_PATH, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def remove_pid():
    try:
        os.remove(PID_PATH)
    except OSError:
        pass


def peak_percent(chunk):
    """Пиковый уровень PCM 16 бит в процентах: видно, идёт ли реальный звук."""
    if len(chunk) < 2:
        return 0
    samples = array.array("h")
    samples.frombytes(chunk[:len(chunk) // 2 * 2])
    peak = 0
    for v in samples:
        a = -v if v < 0 else v
        if a > peak:
            peak = a
    return min(100, peak * 100 // 32768)


class Viewer(object):
    def __init__(self, root, host, port, token, audio=True, embedded=False, *, auto_control=False):
        self.embedded = embedded
        self.root = tk.Frame(root, bg=BG) if embedded else root
        self._closed = False
        self._after_ids = set()
        self._stats_last = (time.monotonic(), 0, 0)
        self.host = host
        self.port = port
        self.token = token
        self.stop = threading.Event()

        self.sock = None
        self.control_lock = threading.Lock()
        self.control_q = queue.Queue(maxsize=32)
        self.authenticated = False
        self.control_capable = False
        self.control_enabled = False
        # Only a phone-initiated GUI handoff may opt in, once per viewer lifetime.
        self.auto_control_pending = auto_control is True
        self.control_epoch = 0
        self.connection_epoch = 0
        self.ui_connection_epoch = 0
        self.gesture = None
        self.rendered_size = None
        self.last_rendered = 0.0
        self.control_message = "управление выключено"
        self.control_status_q = queue.Queue(maxsize=32)
        self.audio_q = queue.Queue(maxsize=100)
        self.audio_enabled = audio
        self.ffplay = None
        self.audio_lock = threading.Lock()
        self.sr = 44100
        self.ch = 2
        self.level = 0
        self.audio_seen = 0

        self.lock = threading.Lock()
        self.latest = None
        self.frames = 0
        self.bytes = 0
        self.status_q = queue.Queue()
        self.status = "подключение…"
        self.status_color = MUTED

        self.codec = ""
        self.vw = 0
        self.vh = 0
        self.ow = 0
        self.oh = 0
        self.h264_config = None
        self.vproc = None
        self.vlock = threading.Lock()

        self.device_name = ""
        self.photo = None
        self.max_w = 460
        self.max_h = 800

        self._build_ui()
        if embedded:
            self.root.viewer = self
            self.root.dispose = self.close
            self.root.bind("<Destroy>", self._on_destroy, add="+")
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._schedule(20, self._pump)
        self._schedule(500, self._tick)
        threading.Thread(target=self._control_loop, daemon=True).start()
        threading.Thread(target=self._net, daemon=True).start()
        threading.Thread(target=self._audio_loop, daemon=True).start()
        threading.Thread(target=self._video_loop, daemon=True).start()

    # ---------- интерфейс ----------

    def _build_ui(self):
        if not getattr(self, "embedded", False):
            self.root.title("Экран телефона — DroidBridge")
            apply_theme(self.root)
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = min(480, max(360, sw // 3))
            h = min(sh - 120, 980)
            self.root.geometry("%dx%d+%d+%d" % (w, h, sw - w - 60, 60))
        self._theme_root = self.root.winfo_toplevel()
        p = self._palette()
        BG, PANEL, TEXT, MUTED, PRIMARY = (p[key] for key in
                                         ("background", "surface", "text", "muted", "primary"))
        self.root.configure(bg=BG)
        self._theme_checks = []

        top = tk.Frame(self.root, bg=PANEL)
        top.pack(side="top", fill="x")

        self.status_label = tk.Label(top, text=self.status, fg=MUTED, bg=PANEL,
                                     anchor="w", font=("Segoe UI", 9))
        self.status_label.pack(side="left", padx=12, pady=8, fill="x", expand=True)

        # Native Tk controls need explicit palette/focus states; ttk theme settings
        # do not affect them. Keep widget layout and all commands unchanged.
        focus_style = dict(takefocus=True, highlightthickness=1,
                           highlightcolor=PRIMARY, highlightbackground=PANEL)
        check_style = dict(bg=PANEL, fg=TEXT, activebackground=PANEL,
                           activeforeground=TEXT, selectcolor=PANEL,
                           disabledforeground=MUTED, bd=0,
                           font=("Segoe UI", 9), **focus_style)
        button_style = dict(bg=BG, fg=TEXT, activebackground=p["surface_alt"],
                            activeforeground=TEXT, disabledforeground=MUTED,
                            relief="flat", overrelief="flat", **focus_style)

        self.on_top = tk.BooleanVar(value=False)
        if not getattr(self, "embedded", False):
            on_top = tk.Checkbutton(top, text="Поверх", variable=self.on_top,
                                    command=self._toggle_top, **check_style)
            on_top.pack(side="right", padx=(0, 6))
            self._theme_checks.append(on_top)

        self.audio_var = tk.BooleanVar(value=self.audio_enabled)
        audio = tk.Checkbutton(top, text="Звук", variable=self.audio_var,
                               command=self._toggle_audio, **check_style)
        audio.pack(side="right", padx=(0, 6))
        self._theme_checks.append(audio)

        controls = tk.Frame(self.root, bg=PANEL)
        controls.pack(side="top", fill="x")
        self.control_var = tk.BooleanVar(value=False)
        self.control_toggle = tk.Checkbutton(
            controls, text="Управлять", variable=self.control_var, command=self._toggle_control,
            state="disabled", **check_style)
        self.control_toggle.pack(side="left", padx=4)
        self.control_widgets = []
        for label, name in (("Назад", "back"), ("Домой", "home"), ("Недавние", "recents")):
            button = tk.Button(controls, text=label, state="disabled",
                               command=lambda n=name: self._queue_control({"action": "global", "name": n}),
                               **button_style)
            button.pack(side="left", padx=2, pady=4)
            self.control_widgets.append(button)
        textbar = tk.Frame(self.root, bg=PANEL)
        textbar.pack(side="top", fill="x")
        self.text_entry = tk.Entry(textbar, state="disabled", bg=PANEL, fg=TEXT,
                                   disabledbackground=BG, disabledforeground=MUTED,
                                   insertbackground=TEXT, selectbackground=PRIMARY,
                                   selectforeground=PANEL, relief="flat", **focus_style)
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(6, 3), pady=3)
        self.text_entry.bind("<Return>", self._send_text)
        send = tk.Button(textbar, text="Текст →", command=self._send_text,
                         state="disabled", **button_style)
        send.pack(side="right", padx=(0, 6))
        self.control_widgets.extend((self.text_entry, send))
        self.control_label = tk.Label(self.root, text=self.control_message, bg=PANEL,
                                      fg=MUTED, anchor="w", font=("Segoe UI", 9), wraplength=440)
        self.control_label.pack(side="top", fill="x", padx=4)

        self.image_label = tk.Label(self.root, bg="#000000", bd=0, highlightthickness=0,
                                    padx=0, pady=0, anchor="center")
        self.image_label.pack(side="top", fill="both", expand=True)
        self.image_label.bind("<ButtonPress-1>", self._pointer_down)
        self.image_label.bind("<ButtonRelease-1>", self._pointer_up)
        self.image_label.bind("<Button-3>", self._pointer_back)
        self.image_label.bind("<MouseWheel>", self._wheel)

        self.root.bind("<Configure>", self._on_resize)
        self._theme_panels = (top, controls, textbar)
        self._theme_checks.append(self.control_toggle)
        self._theme_binding = self._theme_root.bind(
            "<<DroidBridgeThemeChanged>>", self._on_theme_changed, add="+")
        self._on_theme_changed()

    def _palette(self):
        """Use the owning shell's palette; never create a second Tk/controller."""
        owner = self._theme_root
        controller = getattr(owner, "theme_controller", None)
        return (controller.palette if controller is not None else
                getattr(owner, "_droidbridge_palette", PALETTE))

    def _status_foreground(self):
        # Worker queues retain their legacy semantic colors. Resolve them only
        # at paint time so a queued error cannot restore a light-theme color.
        p = self._palette()
        color = getattr(self, "status_color", MUTED)
        return {MUTED: p["muted"], BAD: p["danger"],
                OK: p.get("success", OK)}.get(color, color)

    def _on_theme_changed(self, event=None):
        if getattr(self, "_closed", False):
            return
        p = self._palette()
        self.root.configure(bg=p["background"])
        for panel in self._theme_panels:
            panel.configure(bg=p["surface"])
        self.status_label.configure(bg=p["surface"], fg=self._status_foreground())
        self.control_label.configure(bg=p["surface"], fg=p["muted"])
        focus = dict(highlightcolor=p["primary"], highlightbackground=p["surface"])
        for check in self._theme_checks:
            check.configure(bg=p["surface"], fg=p["text"],
                            activebackground=p["surface"], activeforeground=p["text"],
                            selectcolor=p["surface"], disabledforeground=p["muted"], **focus)
        for button in self.control_widgets:
            if button is self.text_entry:
                continue
            button.configure(bg=p["background"], fg=p["text"],
                             activebackground=p["surface_alt"], activeforeground=p["text"],
                             disabledforeground=p["muted"], **focus)
        self.text_entry.configure(bg=p["surface"], fg=p["text"],
                                  disabledbackground=p["background"], disabledforeground=p["muted"],
                                  insertbackground=p["text"], selectbackground=p["primary"],
                                  selectforeground=p.get("button_text", "#FFFFFF"), **focus)

    def _on_resize(self, event):
        if event.widget is not self.root:
            return
        # Toolbar height is variable; rendering and decoding use the image area only.
        self.max_w = max(1, self.image_label.winfo_width())
        self.max_h = max(1, self.image_label.winfo_height())

    def _toggle_top(self):
        if getattr(self, "embedded", False):
            return
        try:
            self.root.attributes("-topmost", bool(self.on_top.get()))
        except tk.TclError:
            pass

    def _toggle_audio(self):
        self.audio_enabled = bool(self.audio_var.get())
        if not self.audio_enabled:
            self._stop_ffplay()
        log("звук: %s" % ("вкл" if self.audio_enabled else "выкл"))

    def set_status(self, text, color=MUTED):
        self.status_q.put((text, color))

    # ---------- управление (Tk only enqueues; one worker writes) ----------

    def _control_status(self, text):
        try:
            self.control_status_q.put_nowait(text)
        except queue.Full:
            pass

    def _clear_controls_locked(self):
        self.control_epoch += 1
        while True:
            try:
                self.control_q.get_nowait()
            except queue.Empty:
                break

    def _invalidate_connection(self, sock=None):
        with self.control_lock:
            if sock is not None and self.sock is not sock:
                return
            self.authenticated = False
            self.control_capable = False
            self.control_enabled = False
            self.auto_control_pending = False
            self.last_rendered = 0.0
            detached_sock, self.sock = self.sock, None
            self.connection_epoch += 1
            self._clear_controls_locked()
            return detached_sock

    def _toggle_control(self):
        with self.control_lock:
            self.auto_control_pending = False
            self._clear_controls_locked()
            self.control_enabled = control_allowed(
                self.authenticated, self.control_capable, bool(self.control_var.get()))
            enabled = self.control_enabled
        self.gesture = None
        self.control_var.set(enabled)
        self.control_message = "управление включено" if enabled else "управление выключено"

    def _frame_fresh(self):
        return self.last_rendered > 0 and time.monotonic() - self.last_rendered <= 1.5

    def _invalidate_render(self):
        with self.control_lock:
            self.last_rendered = 0.0
            self._clear_controls_locked()

    def _queue_control(self, command, expected_epoch=None):
        try:
            payload = encode_control(command)
        except ValueError as exc:
            self.control_message = str(exc)
            return False
        with self.control_lock:
            if (not control_allowed(self.authenticated, self.control_capable, self.control_enabled)
                    or self.sock is None or self.stop.is_set() or not self._frame_fresh()
                    or (expected_epoch is not None and expected_epoch != self.control_epoch)):
                return False
            try:
                self.control_q.put_nowait((self.sock, self.control_epoch, payload, time.monotonic()))
            except queue.Full:
                self.control_message = "очередь управления занята — повтори действие"
                return False
        return True

    def _control_loop(self):
        while not self.stop.is_set():
            try:
                sock, epoch, payload, enqueued = self.control_q.get(timeout=0.2)
            except queue.Empty:
                continue
            with self.control_lock:
                valid = (sock is self.sock and epoch == self.control_epoch and
                         control_allowed(self.authenticated, self.control_capable, self.control_enabled))
            if not valid or not self._frame_fresh() or time.monotonic() - enqueued > 0.75:
                continue
            try:
                self._send(sock, TYPE_CONTROL, payload)
            except OSError:
                self._invalidate_connection(sock)
                self._control_status("ошибка отправки управления; соединение закрыто")
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

    def _event_point(self, event):
        if self.rendered_size is None:
            return None
        return image_point(event.x, event.y, self.image_label.winfo_width(),
                           self.image_label.winfo_height(), *self.rendered_size)

    def _pointer_down(self, event):
        self.gesture = None
        point = self._event_point(event)
        with self.control_lock:
            if point is not None and control_allowed(
                    self.authenticated, self.control_capable, self.control_enabled):
                self.gesture = (point, event.x, event.y, time.monotonic(),
                                self.control_epoch, self.rendered_size,
                                self.image_label.winfo_width(), self.image_label.winfo_height())

    def _pointer_up(self, event):
        gesture, self.gesture = self.gesture, None
        end = self._event_point(event)
        if gesture is None or end is None:
            return
        start, x, y, began, epoch, size, width, height = gesture
        if (size != self.rendered_size or width != self.image_label.winfo_width()
                or height != self.image_label.winfo_height()):
            return
        distance = ((event.x - x) ** 2 + (event.y - y) ** 2) ** 0.5
        self._queue_control(gesture_command(start, end, time.monotonic() - began, distance), epoch)

    def _pointer_back(self, event):
        if self._event_point(event) is not None:
            self._queue_control({"action": "global", "name": "back"})

    def _wheel(self, event):
        point = self._event_point(event)
        if point is None or not event.delta:
            return
        x, y = point
        # Wheel up moves the finger down, wheel down moves it up.
        y2 = max(0.0, min(1.0, y + (0.25 if event.delta > 0 else -0.25)))
        if y2 != y:
            self._queue_control({"action": "swipe", "x": x, "y": y,
                                 "x2": x, "y2": y2, "duration": 250})
        return "break"

    def _send_text(self, event=None):
        if self._queue_control({"action": "text", "text": self.text_entry.get()}):
            self.text_entry.delete(0, "end")
        return "break"

    def _refresh_controls(self):
        with self.control_lock:
            available = self.authenticated and self.control_capable
            enabled = self.control_enabled
            connection_epoch = self.connection_epoch
        if connection_epoch != self.ui_connection_epoch:
            self.ui_connection_epoch = connection_epoch
            self.gesture = None
            self.rendered_size = None
            self.photo = None
            self.image_label.configure(image="")
        self.control_var.set(enabled)
        if not enabled:
            self.gesture = None
        self.control_toggle.configure(state="normal" if available else "disabled")
        fresh = self._frame_fresh()
        for widget in self.control_widgets:
            widget.configure(state="normal" if enabled and fresh else "disabled")
        if enabled and not fresh:
            self.control_message = "управление приостановлено: жду свежий кадр"
        elif enabled and self.control_message == "управление приостановлено: жду свежий кадр":
            self.control_message = "управление включено"
        if not available:
            self.control_message = ("на телефоне включи службу специальных возможностей и переподключись"
                                    if self.authenticated else "управление недоступно: нет авторизованного соединения")
        while True:
            try:
                self.control_message = self.control_status_q.get_nowait()
            except queue.Empty:
                break
        self.control_label.configure(text=self.control_message,
                                     wraplength=max(200, self.root.winfo_width() - 12))

    # ---------- сеть ----------

    def _net(self):
        delay = 0.3
        while not self.stop.is_set():
            sock = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=3)
            except OSError as e:
                if self.stop.is_set():
                    return
                log("подключение %s:%s - %r" % (self.host, self.port, e))
                self.set_status("жду телефон: %s" % e, BAD)
                time.sleep(delay)
                delay = min(2.0, delay * 1.5)
                continue
            delay = 0.3
            with self.control_lock:
                if self.stop.is_set():
                    sock.close()
                    return
                self.sock = sock
            sock.settimeout(None)
            log("подключено к %s:%s" % (self.host, self.port))
            self.set_status("соединение установлено, жду поток…", OK)
            try:
                hello = json.dumps({"token": self.token, "role": "pc"}).encode("utf-8")
                self._send(sock, TYPE_HELLO, hello)
                while not self.stop.is_set():
                    n, kind = struct.unpack(">IB", self._recv_exact(sock, 5))
                    if n > MAX_PACKET:
                        raise ValueError("пакет слишком большой: %d" % n)
                    if kind == TYPE_CONTROL and n > 8192:
                        raise ValueError("ответ управления слишком большой")
                    payload = self._recv_exact(sock, n) if n else b""
                    if kind == TYPE_HELLO:
                        self._on_hello(payload)
                        continue
                    if not self.authenticated:
                        raise ValueError("поток до авторизации")
                    if kind == TYPE_CONTROL:
                        reply = json.loads(payload.decode("utf-8"))
                        if not isinstance(reply, dict):
                            raise ValueError("неверный ответ управления")
                        if reply.get("ok") is False:
                            self._control_status("телефон: " + str(reply.get("error", "управление недоступно"))[:300])
                    elif kind == TYPE_JPEG:
                        with self.lock:
                            self.latest = payload
                            self.frames += 1
                            self.bytes += len(payload)
                    elif kind == TYPE_H264_CONFIG:
                        self._on_h264_config(payload)
                    elif kind == TYPE_H264:
                        self.bytes += len(payload)
                        self._feed_video(payload)
                    elif kind == TYPE_PCM:
                        try:
                            self.audio_q.put_nowait(payload)
                        except queue.Full:
                            try:
                                self.audio_q.get_nowait()
                            except queue.Empty:
                                pass
                            try:
                                self.audio_q.put_nowait(payload)
                            except queue.Full:
                                pass
            except Exception as e:
                if not self.stop.is_set():
                    log("поток прерван: %r" % (e,))
                    self.set_status("телефон отключился", BAD)
            finally:
                self._invalidate_connection(sock)
                with self.lock:
                    self.latest = None
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass
                self._stop_ffplay()
                self._stop_decoder()
            if not self.stop.is_set():
                self.set_status("переподключение…", MUTED)
                time.sleep(1.0)

    @staticmethod
    def _recv_exact(sock, n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("соединение закрыто")
            buf += chunk
        return buf

    @staticmethod
    def _send(sock, kind, payload):
        sock.sendall(struct.pack(">IB", len(payload), kind) + payload)

    def _on_hello(self, payload):
        info = json.loads(payload.decode("utf-8"))
        got = str(info.get("token", ""))
        if not self.token or not hmac.compare_digest(got, self.token):
            raise ValueError("неверный токен")
        self.device_name = info.get("name") or "телефон"
        self.codec = str(info.get("video") or "jpeg")
        self.vw = int(info.get("w") or 0)
        self.vh = int(info.get("h") or 0)
        self.sr = int(info.get("sr") or 44100)
        self.ch = int(info.get("ch") or 2)
        with self.control_lock:
            if self.stop.is_set():
                self.auto_control_pending = False
                return
            self.authenticated = True
            self.control_capable = info.get("control") is True
            self.control_enabled = self.auto_control_pending and self.control_capable
            self.auto_control_pending = False
            enabled = self.control_enabled
            self._clear_controls_locked()
        self._control_status("управление включено" if enabled else
                             "управление выключено — включи явно" if self.control_capable else
                             "управление недоступно: включи службу на телефоне и переподключись")
        log("поток: %s %sx%s, видео %s, звук %s Гц x%s" % (
            self.device_name, info.get("w"), info.get("h"), self.codec,
            self.sr, self.ch))
        self.set_status("подключено: %s" % self.device_name, OK)

    # ---------- картинка ----------

    def _pump(self):
        if self.stop.is_set():
            return
        while True:
            try:
                text, color = self.status_q.get_nowait()
            except queue.Empty:
                break
            self.status = text
            self.status_color = color

        self._refresh_controls()
        with self.lock:
            data, self.latest = self.latest, None
        if data:
            try:
                if isinstance(data, Image.Image):
                    img = data
                else:
                    img = Image.open(io.BytesIO(data))
                    img.load()
                self.max_w = max(1, self.image_label.winfo_width())
                self.max_h = max(1, self.image_label.winfo_height())
                scale = min(self.max_w / float(img.width),
                            self.max_h / float(img.height), 1.0)
                if scale < 1.0:
                    size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
                    img = img.resize(size, Image.BILINEAR)
                self.photo = ImageTk.PhotoImage(img)
                self.image_label.configure(image=self.photo)
                self.rendered_size = (img.width, img.height)
                self.last_rendered = time.monotonic()
            except Exception as e:
                self._invalidate_render()
                log("кадр не разобран: %r" % (e,))

        self.status_label.configure(text=self._status_text(), fg=self._status_foreground())
        self._schedule(10, self._pump)

    # ---------- видео H.264 ----------

    def _on_h264_config(self, payload):
        with self.vlock:
            self.h264_config = payload
            running = self.vproc is not None and self.vproc.poll() is None
        if running:
            self._stop_decoder()
        log("видео: SPS/PPS %d байт" % len(payload))

    def _ensure_decoder(self):
        with self.vlock:
            if self.stop.is_set():
                return None
            if self.vproc is not None and self.vproc.poll() is None:
                return self.vproc
            self._kill_decoder_locked()
            if not self.vw or not self.vh:
                return None
            exe = MEDIA_TOOLS.ffmpeg
            if not exe or not os.path.isfile(exe):
                log("H.264 недоступен: настрой видео и звук на ПК и открой просмотр заново")
                return None
            self.ow = min(self.vw, self.max_w)
            self.oh = max(2, int(round(self.vh * self.ow / float(self.vw))))
            cmd = [exe, "-hide_banner", "-loglevel", "error",
                   "-fflags", "nobuffer", "-flags", "low_delay",
                   "-probesize", "32", "-analyzeduration", "0",
                   "-f", "h264", "-i", "pipe:0",
                   "-vf", "scale=%d:%d:flags=fast_bilinear" % (self.ow, self.oh),
                   "-fps_mode", "passthrough",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
            try:
                self.vproc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                              stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE,
                                              creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                log("видео: не удалось запустить ffmpeg: %r" % (e,))
                self.vproc = None
                return None
            threading.Thread(target=self._read_stderr, args=(self.vproc,),
                             daemon=True).start()
            proc, config = self.vproc, self.h264_config
        # Pipe writes can block. Never hold vlock here: dispose needs that lock
        # to kill the decoder and unblock its writer. Keep the captured identity
        # rather than accidentally feeding a replacement decoder.
        if config:
            try:
                proc.stdin.write(config)
                proc.stdin.flush()
            except Exception as e:
                log("видео: конфиг не записан: %r" % (e,))
        with self.vlock:
            if self.stop.is_set() or self.vproc is not proc:
                return None
        log("видео: декодер H.264 запущен (%dx%d)" % (self.vw, self.vh))
        return proc

    def _feed_video(self, payload):
        proc = self._ensure_decoder()
        if proc is None:
            return
        try:
            proc.stdin.write(payload)
            proc.stdin.flush()
        except Exception as e:
            log("видео: кадр не отправлен: %r" % (e,))
            self._stop_decoder()

    def _video_loop(self):
        while not self.stop.is_set():
            proc = self.vproc
            if proc is None or self.ow <= 0 or self.oh <= 0:
                time.sleep(0.05)
                continue
            need = self.ow * self.oh * 3
            data = self._read_exact(proc.stdout, need)
            if data is None:
                self._invalidate_render()
                with self.vlock:
                    if self.vproc is proc:
                        self._kill_decoder_locked()
                self.set_status("видео: перезапуск…", BAD)
                time.sleep(0.2)
                continue
            try:
                img = Image.frombytes("RGB", (self.ow, self.oh), data)
            except Exception as e:
                self._invalidate_render()
                log("видео: кадр не собран: %r" % (e,))
                continue
            with self.lock:
                self.latest = img
                self.frames += 1
                first = self.frames == 1
            if first:
                log("видео: первый кадр %dx%d" % (self.ow, self.oh))

    @staticmethod
    def _read_stderr(proc):
        try:
            for raw in proc.stderr:
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    log("ffmpeg: " + line)
        except Exception:
            pass

    @staticmethod
    def _read_exact(stream, n):
        parts = []
        got = 0
        while got < n:
            chunk = stream.read(n - got)
            if not chunk:
                return None
            parts.append(chunk)
            got += len(chunk)
        return b"".join(parts) if len(parts) > 1 else parts[0]

    def _kill_decoder_locked(self):
        proc, self.vproc = self.vproc, None
        if proc is None:
            return
        # Stop the reader before closing the pipe: a worker may hold its write
        # lock while blocked in flush, so closing first can freeze the Tk thread.
        try:
            proc.kill()
        except Exception:
            pass
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

    def _stop_decoder(self):
        self._invalidate_render()
        with self.vlock:
            self._kill_decoder_locked()

    def _status_text(self):
        parts = [self.status]
        if self.frames:
            parts.append("%.0f кадр/с" % self.fps)
            parts.append("%.0f КБ/с" % (self.kbps))
        if self.audio_enabled and self.ffplay is not None and self.ffplay.poll() is None:
            parts.append("звук")
        if self.audio_seen:
            parts.append("%d%%" % self.level)
        return " · ".join(parts)

    # ---------- звук ----------

    def _audio_loop(self):
        while not self.stop.is_set():
            try:
                chunk = self.audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            self.audio_seen += len(chunk)
            level = peak_percent(chunk)
            self.level = max(level, int(self.level * 0.5))
            if not self.audio_enabled:
                continue
            if self.ffplay is None or self.ffplay.poll() is not None:
                self._start_ffplay()
            proc = self.ffplay
            if proc is None:
                continue
            try:
                proc.stdin.write(chunk)
                proc.stdin.flush()
            except Exception as e:
                log("ffplay: %r" % (e,))
                self._stop_ffplay()

    def _start_ffplay(self):
        with self.audio_lock:
            if self.stop.is_set() or not self.audio_enabled:
                return
            exe = MEDIA_TOOLS.ffplay
            if not exe or not os.path.isfile(exe):
                log("Звук недоступен: настрой видео и звук на ПК и открой просмотр заново")
                self.audio_enabled = False
                return
            layout = "mono" if self.ch == 1 else "stereo"
            cmd = [exe, "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit",
                   "-fflags", "nobuffer", "-flags", "low_delay",
                   "-f", "s16le", "-sample_rate", str(self.sr),
                   "-ch_layout", layout, "-"]
            try:
                self.ffplay = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL,
                                               creationflags=CREATE_NO_WINDOW)
                log("звук: ffplay запущен (%d Гц, %d кан.)" % (self.sr, self.ch))
            except Exception as e:
                log("звук: не удалось запустить ffplay: %r" % (e,))
                self.ffplay = None

    def _stop_ffplay(self):
        with self.audio_lock:
            proc, self.ffplay = self.ffplay, None
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

    # ---------- закрытие ----------

    def _schedule(self, delay, callback):
        """Keep every Tk callback owned by this viewer and cancellable on dispose."""
        if self.stop.is_set():
            return
        after_id = None

        def run():
            self._after_ids.discard(after_id)
            if not self.stop.is_set():
                callback()

        after_id = self.root.after(delay, run)
        self._after_ids.add(after_id)

    def _tick(self):
        if self.stop.is_set():
            return
        now = time.monotonic()
        began, previous_frames, previous_bytes = self._stats_last
        dt = now - began
        if dt >= 1.0:
            with self.lock:
                frames, nbytes = self.frames, self.bytes
            self.fps = (frames - previous_frames) / dt
            self.kbps = (nbytes - previous_bytes) / dt / 1024.0
            self._stats_last = (now, frames, nbytes)
        self._schedule(500, self._tick)

    def _on_destroy(self, event):
        if event.widget is self.root:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop.set()
        theme_binding = getattr(self, "_theme_binding", None)
        if theme_binding:
            try:
                self._theme_root.unbind("<<DroidBridgeThemeChanged>>", theme_binding)
            except tk.TclError:
                pass
            self._theme_binding = None
        for after_id in self._after_ids:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._after_ids.clear()
        # Snapshot and detach under the same lock as post-connect publication.
        sock = self._invalidate_connection()
        self.gesture = None
        try:
            if sock:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
        except OSError:
            if sock:
                sock.close()
        self._stop_ffplay()
        self._stop_decoder()
        log("окно закрыто")
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # Статистика: собственный таймер работает и без standalone main().
    fps = 0.0
    kbps = 0.0


def build_viewer_page(parent, host, port, token, audio=True, *, auto_control=False):
    """Return an unpacked Frame with .viewer and an idempotent .dispose().

    The caller owns geometry management and the application window. Disposing
    this page (or destroying its parent) stops its workers and Tk timers only.
    """
    return Viewer(parent, host, port, token, audio=audio, embedded=True,
                  auto_control=auto_control).root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", required=True, help="IP телефона")
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--token-file", default=DEFAULT_TOKEN)
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    try:
        token = read_token(args.token_file)
    except OSError as e:
        log("нет файла токена: %r" % (e,))
        sys.exit(2)

    root = tk.Tk()
    viewer = Viewer(root, args.connect, args.port, token, audio=not args.no_audio)
    write_pid()

    try:
        root.mainloop()
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
