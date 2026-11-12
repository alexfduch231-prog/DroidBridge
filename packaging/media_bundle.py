"""Strict, hash-complete reviewed media kits. No binary in a kit is executed.

Schema 1 is shared with the source-build producer. Hashes establish integrity,
not authorship or license compliance; root release review remains mandatory.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from urllib.parse import urlsplit

MANIFEST = 'media-manifest.json'
MAPS = {'runtime_sha256': 'bin', 'source_sha256': 'sources', 'license_sha256': 'licenses'}
COMPONENT_FIELDS = {'name', 'version', 'license', 'source_url', 'source_paths', 'license_paths'}
ARCHIVES = ('.tar.xz', '.tar.gz', '.tar.bz2', '.tar.zst', '.tgz', '.zip')
RECIPES = {'.sh', '.py', '.ps1', '.md', '.txt'}


def _plain_path(name, prefix):
    if not isinstance(name, str) or not name or any(ord(c) < 32 for c in name):
        raise ValueError('Invalid media path')
    parts = name.split('/')
    reserved = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(10)), *(f'lpt{i}' for i in range(10))}
    if len(parts) < 2 or parts[0] != prefix or any(
            not p or p in {'.', '..'} or p.endswith((' ', '.')) or
            any(c in p for c in '\\:<>"|?*') or p.split('.')[0].lower() in reserved for p in parts):
        raise ValueError('Unsafe media path: ' + name)
    return PurePosixPath(name)


def _no_link(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Media symlink/reparse point forbidden: ' + str(path))
    return info


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest key: ' + key)
        result[key] = value
    return result


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_media_bundle(root, *, staged=False):
    """Return schema-1 manifest after checking the complete original/staged kit."""
    root = Path(root).absolute()
    try:
        for path in [root, *root.parents]:
            _no_link(path)
        if not root.is_dir():
            raise ValueError('Media root must be a directory')
        manifest_path = root / MANIFEST
        if not stat.S_ISREG(_no_link(manifest_path).st_mode):
            raise ValueError('Media manifest must be a regular file')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        if not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'components', *MAPS} or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
            raise ValueError('Unsupported media manifest schema')
        expected = {MANIFEST}
        directories = set()
        seen = set()
        for key, prefix in MAPS.items():
            entries = manifest[key]
            if not isinstance(entries, dict) or not entries:
                raise ValueError('Missing hash map: ' + key)
            for name, digest in entries.items():
                relative = _plain_path(name, prefix)
                if name.casefold() in seen:
                    raise ValueError('Case-insensitive media path collision: ' + name)
                seen.add(name.casefold())
                if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                    raise ValueError('Invalid SHA256: ' + name)
                if key == 'runtime_sha256' and (len(relative.parts) != 2 or relative.suffix.lower() not in {'.exe', '.dll'}):
                    raise ValueError('Runtime files must be bin/*.exe or bin/*.dll')
                actual_name = relative.name if staged and prefix == 'bin' else name
                expected.add(actual_name)
                directories.update(p.as_posix() for p in PurePosixPath(actual_name).parents if p.as_posix() != '.')
        if not {'bin/ffmpeg.exe', 'bin/ffplay.exe'} <= manifest['runtime_sha256'].keys():
            raise ValueError('Both ffmpeg.exe and ffplay.exe are required')
        # Inspect the tree before opening hashed files: no linked parent can escape.
        actual = set()
        for path in root.rglob('*'):
            info = _no_link(path)
            name = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                if name not in directories:
                    raise ValueError('Unexpected media directory: ' + name)
            elif stat.S_ISREG(info.st_mode):
                actual.add(name)
            else:
                raise ValueError('Nonregular media file: ' + name)
        if actual != expected:
            raise ValueError('Media exact allowlist mismatch: ' + str(sorted(actual ^ expected)))
        for key, prefix in MAPS.items():
            for name, digest in manifest[key].items():
                path = root / (PurePosixPath(name).name if staged and prefix == 'bin' else name)
                if _digest(path) != digest:
                    raise ValueError('Media SHA256 mismatch: ' + name)
                if key != 'runtime_sha256':
                    with path.open('rb') as stream:
                        header = stream.read(2)
                    if path.suffix.lower() in {'.exe', '.dll', '.com', '.scr'} or header == b'MZ':
                        raise ValueError('Unexpected runtime PE outside bin: ' + name)
                if key == 'source_sha256' and path.suffix.lower() in RECIPES:
                    text = path.read_text(encoding='utf-8')
                    if '--enable-nonfree' in text.lower():
                        raise ValueError('Nonfree build configuration forbidden')
        sources = manifest['source_sha256']
        if not any(name.lower().endswith(ARCHIVES) for name in sources) or not any(PurePosixPath(name).suffix.lower() in RECIPES for name in sources):
            raise ValueError('Source archives and build recipe required')
        components = manifest['components']
        if not isinstance(components, list) or not components:
            raise ValueError('Component source/license metadata required')
        names = set()
        for component in components:
            if not isinstance(component, dict) or set(component) != COMPONENT_FIELDS:
                raise ValueError('Invalid component metadata')
            for field in ['name', 'version', 'license', 'source_url']:
                value = component[field]
                if not isinstance(value, str) or not value.strip() or 'nonfree' in value.lower() or any(ord(c) < 32 for c in value):
                    raise ValueError('Invalid/nonfree component metadata: ' + field)
            if component['name'].casefold() in names:
                raise ValueError('Duplicate component')
            names.add(component['name'].casefold())
            url = urlsplit(component['source_url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Component source URL must be public HTTPS')
            for field, key in [('source_paths', 'source_sha256'), ('license_paths', 'license_sha256')]:
                paths = component[field]
                if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or p not in manifest[key] for p in paths):
                    raise ValueError('Missing component source/license proof')
            if not any(p.lower().endswith(ARCHIVES) for p in component['source_paths']):
                raise ValueError('Component source archive required')
        if 'ffmpeg' not in names:
            raise ValueError('FFmpeg component metadata required')
        return manifest
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Unreadable media kit: ' + str(exc)) from exc


def stage_media_bundle(root, target):
    """Validate and copy every allowlisted file; flatten bin for runtime resolver."""
    root, target = Path(root), Path(target)
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    manifest = validate_media_bundle(root)
    target.mkdir(parents=True)
    for key in MAPS:
        for name in manifest[key]:
            destination = target / (PurePosixPath(name).name if key == 'runtime_sha256' else name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, destination)
    shutil.copyfile(root / MANIFEST, target / MANIFEST)
    validate_media_bundle(target, staged=True)
    return manifest
