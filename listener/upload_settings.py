"""Local-PC upload destination settings. No network-facing configuration API."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import uuid


class UploadSettingsError(OSError):
    """Safe, path-free error for unavailable or invalid local settings."""


def downloads_folder() -> Path:
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
        raise UploadSettingsError('Could not locate Windows Downloads.')
    try:
        return Path(ctypes.wstring_at(value.value))
    finally:
        ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.ole32.CoTaskMemFree(value)


def _directory(value) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise UploadSettingsError('Choose an existing absolute folder on this PC.')
    try:
        path = Path(value)
        if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or not path.is_dir():
            raise UploadSettingsError('Choose an existing absolute folder on this PC.')
        return path
    except (OSError, ValueError):
        raise UploadSettingsError('The selected upload folder is unavailable.') from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate setting')
        result[key] = value
    return result


def upload_directory(data_dir) -> Path:
    """Reload settings per call. Only an absent config selects Downloads."""
    path = Path(data_dir) / 'upload_settings.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError('Settings too large')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_object)
    except FileNotFoundError:
        # A dangling config symlink is not an absent setting.
        if path.is_symlink():
            raise UploadSettingsError('Upload settings are unavailable.') from None
        try:
            default = Path(downloads_folder())
            if not default.is_absolute():
                raise ValueError('Invalid Downloads location')
            default.mkdir(parents=True, exist_ok=True)
            if not default.is_dir():
                raise OSError('Downloads unavailable')
            return default
        except (OSError, ValueError, TypeError):
            raise UploadSettingsError('Windows Downloads is unavailable.') from None
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise UploadSettingsError('Upload settings are invalid or unavailable.') from None
    if not isinstance(value, dict) or set(value) != {'directory'} or not isinstance(value['directory'], str):
        raise UploadSettingsError('Upload settings are invalid or unavailable.')
    return _directory(value['directory'])


def save_upload_directory(data_dir, path):
    """Atomically persist an existing absolute local directory; never mkdir it."""
    directory = _directory(path)
    temp = None
    try:
        data = Path(data_dir)
        data.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=data,
                                         prefix='.upload-settings-', suffix='.tmp', delete=False) as stream:
            temp = Path(stream.name)
            json.dump({'directory': str(directory)}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, data / 'upload_settings.json')
        temp = None
    except (OSError, ValueError, UnicodeError):
        raise UploadSettingsError('Could not save upload settings.') from None
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def reset_upload_directory(data_dir):
    """Remove the override. The next resolution uses Windows Downloads."""
    try:
        (Path(data_dir) / 'upload_settings.json').unlink(missing_ok=True)
    except OSError:
        raise UploadSettingsError('Could not reset upload settings.') from None
