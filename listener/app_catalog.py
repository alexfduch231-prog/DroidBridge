"""Bounded local application allowlist. Never expose raw records to a client.

There is deliberately no HTTP handler or command execution in this module.
Only the local desktop editor should call save_catalog.
"""
import copy
import json
import ntpath
import os
from pathlib import Path
import re
import tempfile

MAX_CATALOG_BYTES = 1024 * 1024
MAX_APPS = 100
# Android bounds the complete response at 64 KiB; reserve space for its envelope.
MAX_PUBLIC_BYTES = 64000
SUPPORTED_EXTENSIONS = frozenset({'.exe', '.lnk'})
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
_PROCESS = re.compile(r'[^\\/:*?"<>|\x00-\x1f]{1,240}\.exe\Z', re.IGNORECASE)


class CatalogError(ValueError):
    """Safe to display: messages never contain paths or file contents."""


def _text(value, limit, allow_empty=False):
    return (isinstance(value, str) and len(value) <= limit
            and (allow_empty or bool(value.strip()))
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def validate_catalog(value):
    """Validate the whole document, returning a detached copy, preserving extras."""
    if not isinstance(value, dict) or not isinstance(value.get('apps'), list):
        raise CatalogError('Invalid application catalog structure.')
    if len(value['apps']) > MAX_APPS:
        raise CatalogError('Too many applications in catalog.')
    ids = set()
    for item in value['apps']:
        if not isinstance(item, dict):
            raise CatalogError('Invalid application record.')
        aid, name, path = (item.get(key) for key in ('id', 'name', 'path'))
        if not isinstance(aid, str) or not _ID.fullmatch(aid) or aid.lower() in ids:
            raise CatalogError('Invalid or duplicate application ID.')
        ids.add(aid.lower())
        if not _text(name, 200) or not _text(path, 32767):
            raise CatalogError('Invalid application name or path.')
        if ntpath.splitext(path)[1].lower() not in SUPPORTED_EXTENSIONS or '://' in path:
            raise CatalogError('Only local EXE and LNK application paths are supported.')
        # Legacy variables/relative paths remain valid; the picker only adds absolute files.
        for key in ('cwd', 'task'):
            if key in item and item[key] is not None and not _text(item[key], 32767, True):
                raise CatalogError('Invalid application options.')
        if 'args' in item and item['args'] is not None:
            if (not isinstance(item['args'], list) or len(item['args']) > 256
                    or any(not _text(arg, 32767, True) for arg in item['args'])):
                raise CatalogError('Invalid application arguments.')
        if 'process' in item and item['process'] is not None:
            procs = item['process']
            if (not isinstance(procs, list) or len(procs) > 64
                    or any(not isinstance(proc, str) or not _PROCESS.fullmatch(proc) for proc in procs)):
                raise CatalogError('Invalid application process names.')
    return copy.deepcopy(value)


def load_catalog(path):
    """Read at most 1 MiB. Missing files represent a fresh empty allowlist."""
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CATALOG_BYTES + 1)
    except FileNotFoundError:
        return {'apps': []}
    except OSError:
        raise CatalogError('Application catalog could not be read.') from None
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogError('Application catalog exceeds the size limit.')
    try:
        value = json.loads(raw.decode('utf-8-sig'))
        return validate_catalog(value)
    except CatalogError:
        raise
    except (ValueError, RecursionError):
        raise CatalogError('Application catalog contains invalid JSON.') from None


def public_catalog(path):
    """Only these three fields may be serialized to the phone."""
    result = [{'id': item['id'], 'name': item['name'], 'can_close': bool(item.get('process'))}
              for item in load_catalog(path)['apps']]
    # ASCII escaping is the worst case for JSON serialization and Unicode names.
    if len(json.dumps(result, ensure_ascii=True).encode('ascii')) > MAX_PUBLIC_BYTES:
        raise CatalogError('Application list exceeds the phone response limit.')
    return result


def save_catalog(path, value):
    """Local-only atomic replacement; any failure leaves the previous file intact."""
    value = validate_catalog(value)
    try:
        raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError, RecursionError):
        raise CatalogError('Application catalog cannot be serialized.') from None
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogError('Application catalog exceeds the size limit.')
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='wb', prefix='.apps-', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise CatalogError('Application catalog could not be saved.') from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass
