"""Read-only Windows shell icons for validated local catalog IDs.

No request path is accepted, no processes are started, and no network resources
are resolved. Native extraction is serialized and cache storage is bounded.
"""
from collections import OrderedDict
import ctypes
from ctypes import wintypes as W
import io
import ntpath
import os
from pathlib import Path
import re
import struct
import threading
import time

from PIL import Image
from app_catalog import load_catalog

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
_MAX_LINK = 1024 * 1024


def _local(path):
    path = os.path.abspath(os.path.expandvars(str(path)))
    if (path.startswith(('\\\\', '//')) or '://' in path or '\x00' in path
            or path.startswith(('\\?\\', '\\.\\'))):
        raise ValueError('Not a local file')
    if os.name == 'nt':
        drive = ntpath.splitdrive(path)[0]
        if not drive or len(drive) != 2 or path.count(':') != 1:
            raise ValueError('Not a local drive')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetDriveTypeW.argtypes = [W.LPCWSTR]
        kernel.GetDriveTypeW.restype = W.UINT
        if kernel.GetDriveTypeW(drive + '\\') not in (2, 3, 6):
            raise ValueError('Not a local drive')
    # Never follow a reparse point: even realpath() could touch a remote target.
    parts = Path(path)
    for component in reversed((parts,) + tuple(parts.parents)):
        stat = os.lstat(component)
        if getattr(stat, 'st_file_attributes', 0) & 0x400 or os.path.islink(component):
            raise ValueError('Reparse points are unsupported')
    return path


def _identity(path):
    stat = os.stat(path)
    if not os.path.isfile(path):
        raise ValueError('Not a file')
    return (path, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _link_dependencies(path):
    """Parse only local filesystem links; never ask COM to resolve a target.

    Unrecognized/malformed links fail closed to the client's generic icon.
    The shell never receives the link itself: only a validated local target or
    explicit custom icon resource. Opaque ID lists cannot trigger resolution.
    """
    with open(path, 'rb') as stream:
        data = stream.read(_MAX_LINK + 1)
    if len(data) > _MAX_LINK or len(data) < 76 or struct.unpack_from('<I', data)[0] != 76:
        raise ValueError('Invalid shortcut')
    if data[4:20] != bytes.fromhex('0114020000000000c000000000000046'):
        raise ValueError('Invalid shortcut')
    # Reject network references anywhere, including environment/extra-data blocks.
    for text in (data.decode('latin1'), data.decode('utf-16-le', errors='ignore')):
        if '\\\\' in text or '://' in text or '//' in text:
            raise ValueError('Network shortcut')
    flags = struct.unpack_from('<I', data, 20)[0]
    offset = 76
    if flags & 1:
        offset += 2 + struct.unpack_from('<H', data, offset)[0]
    target = None
    if flags & 2:
        length, header, link_flags = struct.unpack_from('<III', data, offset)
        if length < 28 or header < 28 or offset + length > len(data) or link_flags & 2:
            raise ValueError('Unsupported shortcut target')
        block = data[offset:offset + length]
        ansi_offset = struct.unpack_from('<I', block, 16)[0]
        unicode_offset = struct.unpack_from('<I', block, 28)[0] if header >= 36 else 0
        if unicode_offset:
            if unicode_offset >= len(block):
                raise ValueError('Invalid shortcut target')
            text = block[unicode_offset:].decode('utf-16-le', errors='strict')
            target = text.split('\0', 1)[0]
        elif ansi_offset:
            target = block[ansi_offset:].split(b'\0', 1)[0].decode('mbcs' if os.name == 'nt' else 'latin1')
        offset += length
    strings = {}
    for bit, name in ((4, 'name'), (8, 'relative'), (16, 'cwd'), (32, 'args'), (64, 'icon')):
        if flags & bit:
            count = struct.unpack_from('<H', data, offset)[0]; offset += 2
            size = count * (2 if flags & 128 else 1)
            if offset + size > len(data):
                raise ValueError('Invalid shortcut string')
            strings[name] = data[offset:offset + size].decode('utf-16-le' if flags & 128 else ('mbcs' if os.name == 'nt' else 'latin1'))
            offset += size
    # Environment target/icon blocks need shell expansion; conservatively avoid them.
    while offset + 4 <= len(data):
        size = struct.unpack_from('<I', data, offset)[0]
        if size == 0:
            break
        if size < 8 or offset + size > len(data):
            raise ValueError('Invalid shortcut extra data')
        signature = struct.unpack_from('<I', data, offset + 4)[0]
        if signature in (0xA0000001, 0xA0000007):
            raise ValueError('Unsupported environment shortcut')
        offset += size
    if target is None:
        relative = strings.get('relative')
        if not relative:
            raise ValueError('No local target')
        target = os.path.join(strings.get('cwd') or os.path.dirname(path), relative)
    target = _local(target)
    if ntpath.splitext(target)[1].lower() != '.exe':
        raise ValueError('Unsupported shortcut target')
    dependencies = [_identity(target)]
    source = target
    if strings.get('icon'):
        icon = strings['icon']
        if not ntpath.isabs(icon):
            icon = os.path.join(os.path.dirname(path), icon)
        icon = _local(icon)
        dependencies.append(_identity(icon))
        source = (icon, struct.unpack_from('<i', data, 56)[0])
    return source, tuple(dependencies)


def _valid_png(data):
    if not isinstance(data, bytes) or not data or len(data) > 65536 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != 'PNG' or not (0 < image.width <= 64 and 0 < image.height <= 64):
                return False
            image.verify()
        return True
    except (OSError, ValueError):
        return False


class IconCache:
    def __init__(self, extractor=None):
        self._extractor = extractor
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, catalog, app_id):
        if not isinstance(app_id, str) or not _ID.fullmatch(app_id):
            return None
        # One lock bounds native shell concurrency, and coalesces duplicate misses.
        with self._lock:
            try:
                document = load_catalog(catalog)
                item = next((x for x in document['apps'] if x['id'] == app_id), None)
                if item is None:
                    return None
                path = _local(item['path'])
                extension = ntpath.splitext(path)[1].lower()
                if extension not in ('.exe', '.lnk'):
                    return None
                source, dependencies = _link_dependencies(path) if extension == '.lnk' else (path, ())
                key = (_identity(os.path.abspath(catalog)), app_id, _identity(path), dependencies)
                now = time.monotonic()
                if key in self._cache:
                    data, created = self._cache.pop(key)
                    # Refresh shell/resource changes even when metadata is unchanged.
                    if now - created < 30:
                        self._cache[key] = (data, created)
                        return data
                data = (self._extractor or extract_icon)(source)
                if not _valid_png(data):
                    data = None
                self._cache[key] = (data, now)
                while len(self._cache) > 64:
                    self._cache.popitem(last=False)
                return data
            except Exception:
                # Shell/invalid-catalog errors must never disclose local paths.
                return None


def extract_icon(path):
    """Render HICON onto black/white DIBs to recover straight RGBA reliably."""
    if os.name != 'nt':
        return None
    resource = isinstance(path, tuple)
    index = path[1] if resource else 0
    path = _local(path[0] if resource else path)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    class SHFILEINFO(ctypes.Structure):
        _fields_ = [('hIcon', W.HICON), ('iIcon', ctypes.c_int), ('attributes', W.DWORD),
                    ('displayName', W.WCHAR * 260), ('typeName', W.WCHAR * 80)]
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                    ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                    ('sizeImage', W.DWORD), ('xppm', W.LONG), ('yppm', W.LONG),
                    ('used', W.DWORD), ('important', W.DWORD)]
    class BITMAPINFO(ctypes.Structure):
        _fields_ = [('header', BITMAPINFOHEADER), ('colors', W.DWORD * 3)]
    shell.SHGetFileInfoW.argtypes = [W.LPCWSTR, W.DWORD, ctypes.POINTER(SHFILEINFO), W.UINT, W.UINT]
    shell.SHGetFileInfoW.restype = ctypes.c_size_t
    user.DestroyIcon.argtypes = [W.HICON]; user.DestroyIcon.restype = W.BOOL
    user.DrawIconEx.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, W.HICON, ctypes.c_int, ctypes.c_int, W.UINT, W.HBRUSH, W.UINT]
    user.DrawIconEx.restype = W.BOOL
    gdi.CreateCompatibleDC.argtypes = [W.HDC]; gdi.CreateCompatibleDC.restype = W.HDC
    gdi.DeleteDC.argtypes = [W.HDC]; gdi.DeleteDC.restype = W.BOOL
    gdi.CreateDIBSection.argtypes = [W.HDC, ctypes.POINTER(BITMAPINFO), W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
    gdi.CreateDIBSection.restype = W.HBITMAP
    gdi.SelectObject.argtypes = [W.HDC, W.HANDLE]; gdi.SelectObject.restype = W.HANDLE
    gdi.DeleteObject.argtypes = [W.HANDLE]; gdi.DeleteObject.restype = W.BOOL
    gdi.GdiFlush.argtypes = []; gdi.GdiFlush.restype = W.BOOL
    shell.ExtractIconExW.argtypes = [W.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.HICON), ctypes.POINTER(W.HICON), W.UINT]
    shell.ExtractIconExW.restype = W.UINT
    info = SHFILEINFO()
    small = W.HICON()
    dc = bitmap = old = None
    try:
        if resource:
            large = W.HICON()
            shell.ExtractIconExW(path, index, ctypes.byref(large), ctypes.byref(small), 1)
            info.hIcon = large.value
        else:
            shell.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), 0x100)
        if not info.hIcon:
            return None
        dc = gdi.CreateCompatibleDC(None)
        if not dc:
            return None
        bmi = BITMAPINFO(); bmi.header = BITMAPINFOHEADER(40, 64, -64, 1, 32, 0, 64 * 64 * 4, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not bitmap or not bits.value:
            return None
        old = gdi.SelectObject(dc, bitmap)
        if not old or old == ctypes.c_void_p(-1).value:
            old = None
            return None
        renders = []
        for fill in (0, 255):
            ctypes.memset(bits, fill, 64 * 64 * 4)
            if not user.DrawIconEx(dc, 0, 0, info.hIcon, 64, 64, 0, None, 3):
                return None
            if not gdi.GdiFlush():
                return None
            renders.append(ctypes.string_at(bits, 64 * 64 * 4))
        black, white = renders
        rgba = bytearray(64 * 64 * 4)
        for i in range(0, len(rgba), 4):
            alpha = 255 - max(0, min(255, max(white[i + c] - black[i + c] for c in range(3))))
            rgba[i:i + 4] = bytes([min(255, (black[i + c] * 255 + alpha // 2) // alpha) if alpha else 0 for c in (2, 1, 0)] + [alpha])
        image = Image.frombytes('RGBA', (64, 64), bytes(rgba))
        out = io.BytesIO(); image.save(out, format='PNG')
        data = out.getvalue()
        return data if _valid_png(data) else None
    finally:
        if old:
            gdi.SelectObject(dc, old)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if dc:
            gdi.DeleteDC(dc)
        if small.value and small.value != info.hIcon:
            user.DestroyIcon(small)
        if info.hIcon:
            user.DestroyIcon(info.hIcon)


ICONS = IconCache()


def get_icon(catalog, app_id):
    return ICONS.get(catalog, app_id)
