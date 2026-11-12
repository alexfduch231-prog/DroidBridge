"""Small allowlisted appearance preferences; registry access is read-only."""
import json
import os
from pathlib import Path
import sys
import tempfile

THEME_MODES = ('system', 'light', 'dark', 'ocean', 'forest', 'plum')
MAX_SETTINGS_BYTES = 8192


def load_theme_mode(data_dir) -> str:
    try:
        with (Path(data_dir) / 'theme_settings.json').open('rb') as stream:
            raw = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(raw) > MAX_SETTINGS_BYTES:
            return 'system'
        value = json.loads(raw)
        if (isinstance(value, dict) and type(value.get('schema')) is int
                and value['schema'] == 1 and isinstance(value.get('mode'), str)
                and value['mode'] in THEME_MODES):
            return value['mode']
    except (OSError, ValueError, UnicodeError, RecursionError):
        pass
    return 'system'


def save_theme_mode(data_dir, mode):
    if not isinstance(mode, str) or mode not in THEME_MODES:
        raise ValueError('Неизвестная тема оформления')
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.theme-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'schema': 1, 'mode': mode}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / 'theme_settings.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def system_theme() -> str:
    if sys.platform != 'win32':
        return 'light'
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
                            0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        if kind == winreg.REG_DWORD and type(value) is int and value == 0:
            return 'dark'
    except (ImportError, OSError):
        pass
    return 'light'
