"""Authenticated raw-body uploads. No external dependencies."""
import ctypes
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid
from urllib.parse import unquote, urlparse

MAX_BYTES = 50 * 1024**3
_UPLOAD_SLOTS = threading.BoundedSemaphore(2)


def downloads_folder():
    """Use Windows Known Folders, including redirected Downloads."""
    if os.name != 'nt':
        return Path.home() / 'Downloads'
    class GUID(ctypes.Structure):
        _fields_ = [('data', ctypes.c_ubyte * 16)]
    guid = GUID()
    guid.data[:] = uuid.UUID('374de290-123f-4565-9164-39c4925e467b').bytes_le
    value = ctypes.c_void_p()
    fn = ctypes.windll.shell32.SHGetKnownFolderPath
    fn.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p,
                   ctypes.POINTER(ctypes.c_void_p)]
    fn.restype = ctypes.c_long
    if fn(ctypes.byref(guid), 0, None, ctypes.byref(value)) != 0:
        raise OSError('Не удалось определить папку «Загрузки» Windows')
    try:
        return Path(ctypes.wstring_at(value.value))
    finally:
        ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.ole32.CoTaskMemFree(value)


def _filename(encoded):
    try:
        name = unquote(encoded, encoding='utf-8', errors='strict')
    except (UnicodeError, ValueError):
        raise ValueError('Некорректное имя файла')
    base = name.split('.')[0].upper()
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
    reserved.update('COM' + str(i) for i in range(1, 10))
    reserved.update('LPT' + str(i) for i in range(1, 10))
    if (not name or len(name.encode('utf-16-le')) > 360 or name in ('.', '..')
            or name.endswith((' ', '.')) or base.rstrip(' ') in reserved
            or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)):
        raise ValueError('Недопустимое имя файла для Windows')
    return name


def _reply(handler, status, payload):
    handler.close_connection = True
    handler.send_bytes(status, 'application/json; charset=utf-8',
                       json.dumps(payload, ensure_ascii=False).encode('utf-8'))


def handle_upload(handler):
    temp = None
    acquired = False
    try:
        if urlparse(handler.path).path != '/upload':
            _reply(handler, 404, {'ok': False, 'error': 'Маршрут не найден'})
            return
        expected = ('Bearer ' + handler.server.token).encode('utf-8')
        actual = handler.headers.get('Authorization', '').encode('utf-8')
        if not handler.server.token or not hmac.compare_digest(actual, expected):
            _reply(handler, 403, {'ok': False, 'error': 'Ключ не подошёл'})
            return
        if handler.headers.get('Transfer-Encoding'):
            raise ValueError('Требуется Content-Length, без Transfer-Encoding')
        lengths = handler.headers.get_all('Content-Length', [])
        if not lengths:
            _reply(handler, 411, {'ok': False, 'error': 'Не указан размер файла'})
            return
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,20}', lengths[0]):
            raise ValueError('Некорректный размер файла')
        length = int(lengths[0])
        if length > MAX_BYTES:
            _reply(handler, 413, {'ok': False, 'error': 'Максимальный размер — 50 ГиБ'})
            return
        name = _filename(handler.headers.get('X-File-Name', ''))
        acquired = _UPLOAD_SLOTS.acquire(blocking=False)
        if not acquired:
            _reply(handler, 429, {'ok': False, 'error': 'Уже идут две загрузки. Повтори позже'})
            return
        root = getattr(handler.server, 'downloads_dir', None)
        root = Path(root) if root is not None else downloads_folder()
        root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(root).free < length + 16 * 1024**2:
            _reply(handler, 507, {'ok': False, 'error': 'Недостаточно места на ПК'})
            return
        handler.connection.settimeout(60)
        with tempfile.NamedTemporaryFile(dir=root, prefix='.pcmote-', suffix='.part', delete=False) as out:
            temp = Path(out.name)
            remaining = length
            while remaining:
                block = handler.rfile.read(min(256 * 1024, remaining))
                if not block:
                    raise ValueError('Передача прервана: файл получен не полностью')
                out.write(block)
                remaining -= len(block)
        stem, suffix = os.path.splitext(name)
        for index in range(10000):
            target = root / (name if index == 0 else '%s (%d)%s' % (stem, index, suffix))
            try:
                # NT rename refuses an existing target; POSIX hard-link is also no-clobber.
                if os.name == 'nt':
                    os.rename(temp, target)
                else:
                    os.link(temp, target)
                    temp.unlink()
                temp = None
                break
            except FileExistsError:
                continue
        else:
            raise OSError('Слишком много файлов с таким именем')
        _reply(handler, 201, {'ok': True, 'name': target.name, 'path': str(target), 'size': length})
    except (ValueError, UnicodeError) as exc:
        _reply(handler, 400, {'ok': False, 'error': str(exc)})
    except TimeoutError:
        _reply(handler, 408, {'ok': False, 'error': 'Превышено время ожидания данных'})
    except OSError:
        _reply(handler, 500, {'ok': False, 'error': 'Не удалось сохранить файл на ПК'})
    finally:
        try:
            if temp is not None:
                temp.unlink(missing_ok=True)
        finally:
            if acquired:
                _UPLOAD_SLOTS.release()
