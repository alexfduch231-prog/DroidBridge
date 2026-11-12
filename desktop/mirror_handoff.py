"""Bounded, private, local-file mirror handoff to the existing main window.

This is a single-latest request, not a command channel. No network listener,
credentials, process execution or automatic GUI startup belongs here. Same-user
processes are trusted as they already have access to the application's token.
"""
from dataclasses import dataclass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time


_REQUEST = 'mirror-request.json'
_HEARTBEAT = 'mirror-gui-heartbeat.json'
_LIMIT = 1024
_MAX_AGE = 10.0
_ID = re.compile(r'[0-9a-f]{32}\Z')
_OPEN_GUI = 'Открой главное окно DroidBridge'


@dataclass(frozen=True)
class MirrorRequest:
    host: str
    port: int
    nonce: str
    created: float


def _plain(path):
    info = path.lstat()
    return not (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400)


def _directory(data):
    path = Path(data).absolute()
    # Do not resolve(): that would hide a symlink or Windows junction.
    if any(not _plain(parent) for parent in (path, *path.parents)):
        raise ValueError('Unsafe handoff directory')
    if not path.is_dir():
        raise ValueError('Handoff directory is unavailable')
    return path


def _read(path):
    if not _plain(path):
        raise ValueError('Unsafe handoff file')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > _LIMIT or before.st_nlink != 1:
        raise ValueError('Invalid handoff file')
    if os.name != 'nt' and (before.st_uid != os.getuid() or before.st_mode & 0o077):
        raise ValueError('Handoff file is not private')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(before, opened):
            raise ValueError('Handoff file changed')
        body = stream.read(_LIMIT + 1)
    if len(body) > _LIMIT:
        raise ValueError('Oversize handoff')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result
    try:
        value = json.loads(body.decode('utf-8'), object_pairs_hook=unique)
    except RecursionError as error:
        raise ValueError('Nested handoff message') from error
    if not isinstance(value, dict):
        raise ValueError('Expected handoff object')
    return value


def _private_windows(path):
    """Protect the temporary file before publishing it (owner and SYSTEM only)."""
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    apply = advapi.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    apply.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not convert('D:P(A;;FA;;;SY)(A;;FA;;;OW)', 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not apply(str(path), 0x4 | 0x80000000, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


def _atomic(data, name, payload):
    path = _directory(data) / name
    if path.exists() or path.is_symlink():
        if not _plain(path) or not stat.S_ISREG(path.lstat().st_mode) or path.lstat().st_nlink != 1:
            raise ValueError('Unsafe handoff target')
    body = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(body) > _LIMIT:
        raise ValueError('Oversize handoff')
    fd, temporary = tempfile.mkstemp(prefix='.mirror-', suffix='.tmp', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _private_windows(temporary)
            stream.write(body)
            stream.flush()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fresh(value, now):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= now - value <= _MAX_AGE


def _identifier(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _address(host, port):
    if not isinstance(host, str) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid mirror address')
    # Scoped IPv6 literals contain an interface name; accept plain IPs only.
    if '%' in host:
        raise ValueError('Invalid mirror address')
    return str(ipaddress.ip_address(host))


def request_mirror(data_dir, host, port):
    """Publish one IP/port request only while a main-window heartbeat is fresh."""
    try:
        host = _address(host, port)
        data = _directory(data_dir)
        heartbeat = _read(data / _HEARTBEAT)
        if (set(heartbeat) != {'owner', 'created'} or not _identifier(heartbeat['owner'])
                or not _fresh(heartbeat['created'], time.time())):
            return False, _OPEN_GUI
        _atomic(data, _REQUEST, dict(nonce=secrets.token_hex(16), owner=heartbeat['owner'],
                                    host=host, port=port, created=time.time()))
        return True, ''
    except (OSError, ValueError, TypeError, OverflowError):
        return False, _OPEN_GUI


class GuiMirrorHandoff:
    """Tk owner calls heartbeat/consume on its timer and close during cleanup."""
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.owner = secrets.token_hex(16)
        self._seen = {}
        self._closed = False

    def heartbeat(self):
        if self._closed:
            return False
        try:
            _atomic(self.data_dir, _HEARTBEAT, dict(owner=self.owner, created=time.time()))
            return True
        except (OSError, ValueError, TypeError):
            return False

    def consume(self):
        if self._closed:
            return None
        path = None
        try:
            path = _directory(self.data_dir) / _REQUEST
            # Never unlink/follow an unsafe leaf, including a Windows junction.
            if not _plain(path):
                return None
            payload = _read(path)
            # Remove before delivery, but do not remove a replaced newer request.
            current = _read(path)
            if payload != current:
                return None
            path.unlink()
            now = time.time()
            self._seen = {nonce: stamp for nonce, stamp in self._seen.items() if now - stamp <= _MAX_AGE}
            if (set(payload) != {'nonce', 'owner', 'host', 'port', 'created'}
                    or payload['owner'] != self.owner or not _identifier(payload['nonce'])
                    or not _fresh(payload['created'], now) or payload['nonce'] in self._seen):
                return None
            host = _address(payload['host'], payload['port'])
            self._seen[payload['nonce']] = payload['created']
            return MirrorRequest(host, payload['port'], payload['nonce'], payload['created'])
        except (OSError, ValueError, TypeError, OverflowError):
            if path is not None:
                try:
                    if _plain(path) and stat.S_ISREG(path.lstat().st_mode):
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
            return None

    def close(self):
        self._closed = True
        for name in (_HEARTBEAT, _REQUEST):
            try:
                path = _directory(self.data_dir) / name
                if _read(path).get('owner') == self.owner:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError):
                pass
        self._seen.clear()
