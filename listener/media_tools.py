"""Shared media discovery/settings. No UI, downloads, or execution on discovery."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class MediaToolsError(ValueError):
    """A configured media installation is unavailable or failed its probe."""


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: str | None
    ffplay: str | None
    source: str


SETTINGS_NAME = 'media_settings.json'


def _directory_pair(directory):
    folder = Path(directory)
    if not folder.is_absolute():
        raise MediaToolsError('Выбери существующую папку с ffmpeg.exe и ffplay.exe.')
    for candidate in (folder, folder / 'bin'):
        if all((candidate / name).is_file() for name in ('ffmpeg.exe', 'ffplay.exe')):
            return MediaTools(str(candidate / 'ffmpeg.exe'), str(candidate / 'ffplay.exe'), 'configured')
    raise MediaToolsError('В выбранной папке нет обоих файлов: ffmpeg.exe и ffplay.exe. Выбери папку bin.')


def _same_installation(ffmpeg, ffplay):
    """PATH links may be used, but must not hide two different installations."""
    if not ffmpeg or not ffplay:
        return False
    if Path(ffmpeg).name.lower() not in ('ffmpeg', 'ffmpeg.exe'):
        return False
    if Path(ffplay).name.lower() not in ('ffplay', 'ffplay.exe'):
        return False
    try:
        return (Path(ffmpeg).parent == Path(ffplay).parent
                and Path(ffmpeg).resolve().parent == Path(ffplay).resolve().parent)
    except (OSError, RuntimeError):
        return False


def _automatic_pair(directory, source):
    folder = Path(directory)
    if not folder.is_absolute():
        return None
    names = [('ffmpeg.exe', 'ffplay.exe')]
    if os.name != 'nt':
        names.append(('ffmpeg', 'ffplay'))
    for ffmpeg_name, ffplay_name in names:
        ffmpeg, ffplay = folder / ffmpeg_name, folder / ffplay_name
        if (ffmpeg.is_file() and ffplay.is_file()
                and _same_installation(str(ffmpeg), str(ffplay))):
            if ffmpeg_name == 'ffmpeg' and not all(os.access(path, os.X_OK) for path in (ffmpeg, ffplay)):
                continue
            return MediaTools(str(ffmpeg), str(ffplay), source)
    return None


def _discover_automatic_tools():
    ffmpeg, ffplay = shutil.which('ffmpeg'), shutil.which('ffplay')
    if _same_installation(ffmpeg, ffplay):
        return MediaTools(ffmpeg, ffplay, 'path')
    # A partial earlier PATH entry must not mask a complete later installation.
    # Only explicit, absolute PATH directories are inspected; never the cwd.
    for entry in os.environ.get('PATH', '').split(os.pathsep):
        if entry:
            pair = _automatic_pair(entry, 'path')
            if pair is not None:
                return pair
    locations = (
        ('LOCALAPPDATA', ('Programs', 'FFmpeg', 'bin')),
        ('LOCALAPPDATA', ('Microsoft', 'WinGet', 'Links')),
        ('PROGRAMFILES', ('ffmpeg', 'bin')),
        ('ChocolateyInstall', ('bin',)),
    )
    directories = []
    for variable, suffix in locations:
        base = os.environ.get(variable)
        if base and Path(base).is_absolute():
            directories.append(Path(base).joinpath(*suffix))
    if os.name == 'nt':
        directories.append(Path('C:/ffmpeg/bin'))
    for directory in directories:
        pair = _automatic_pair(directory, 'detected')
        if pair is not None:
            return pair
    return MediaTools(None, None, 'path')


def resolve_media_tools(data_dir, *, media_dir=None) -> MediaTools:
    """Snapshot discovery: explicit config, bundle, paired PATH, standard installs.

    Discovery only inspects file metadata: no scans, execution or downloads.
    Invalid explicit settings fail closed instead of falling back.
    """
    settings = Path(data_dir) / SETTINGS_NAME
    try:
        with settings.open('rb') as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise MediaToolsError('Настройки видео и звука повреждены. Выбери папку заново или сбрось настройки.')
        config = json.loads(raw.decode('utf-8'))
    except FileNotFoundError:
        # A broken symlink is still an explicit configuration, not an absent one.
        if os.path.lexists(settings):
            raise MediaToolsError('Настройки видео и звука недоступны. Выбери папку заново или сбрось настройки.') from None
    except (OSError, ValueError, RecursionError):
        raise MediaToolsError('Настройки видео и звука повреждены. Выбери папку заново или сбрось настройки.') from None
    else:
        if (not isinstance(config, dict) or config.get('version') != 1
                or not isinstance(config.get('directory'), str) or not config['directory']):
            raise MediaToolsError('Настройки видео и звука повреждены. Выбери папку заново или сбрось настройки.')
        return _directory_pair(config['directory'])
    if media_dir is None:
        root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        media_dir = root / 'media'
    try:
        pair = _directory_pair(Path(media_dir).absolute())
        return MediaTools(pair.ffmpeg, pair.ffplay, 'distribution')
    except MediaToolsError:
        return _discover_automatic_tools()


def validate_media_directory(directory, *, timeout=5.0) -> MediaTools:
    """Execute only explicitly selected programs, bounded and never via a shell."""
    try:
        tools = _directory_pair(directory)
        for executable in (tools.ffmpeg, tools.ffplay):
            result = subprocess.run([executable, '-version'], shell=False, timeout=timeout,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode != 0:
                raise MediaToolsError('ffmpeg.exe или ffplay.exe не прошёл проверку -version. Выбери исправную сборку.')
        return tools
    except (OSError, subprocess.SubprocessError):
        raise MediaToolsError('Не удалось проверить ffmpeg.exe и ffplay.exe за отведённое время. Выбери исправную сборку.') from None


def save_media_directory(data_dir, directory, *, timeout=5.0) -> MediaTools:
    """Validate first, then atomically replace the local-only settings file."""
    tools = validate_media_directory(directory, timeout=timeout)
    temporary = None
    try:
        data = Path(data_dir)
        data.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=data,
                                         prefix='.media-settings-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': 1, 'directory': str(Path(tools.ffmpeg).parent)}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, data / SETTINGS_NAME)
    except OSError:
        raise MediaToolsError('Не удалось сохранить настройки видео и звука. Проверь доступ к папке данных.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return tools


def reset_media_directory(data_dir) -> None:
    """Remove only media settings, leaving pairing and all other data intact."""
    try:
        (Path(data_dir) / SETTINGS_NAME).unlink(missing_ok=True)
    except OSError:
        raise MediaToolsError('Не удалось сбросить настройки видео и звука.') from None
