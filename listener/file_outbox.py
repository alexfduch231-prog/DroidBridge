"""Local-only enqueue, authenticated ID-only download transport storage."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
import uuid

CHUNK_BYTES = 4 * 1024**2
MAX_BYTES = 50 * 1024**3
MAX_ITEMS = 32
TTL = 7 * 86400
_LOCK = threading.RLock()
_STAGE_LOCK = threading.Lock()

class OutboxError(ValueError):
    pass

class Outbox:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'file-outbox'

    def _directory(self, ident):
        if not isinstance(ident, str) or not re.fullmatch('[0-9a-f]{32}', ident):
            raise OutboxError('Unknown transfer')
        directory = self.root / ident
        if directory.is_symlink():
            raise OutboxError('Invalid transfer storage')
        return directory

    def _load(self, ident):
        directory = self._directory(ident)
        try:
            meta_path = directory / 'metadata.json'
            if meta_path.is_symlink() or meta_path.stat().st_size > 4096:
                raise ValueError()
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            if (not isinstance(meta, dict) or meta.get('id') != ident or type(meta.get('size')) is not int
                    or not 0 <= meta['size'] <= MAX_BYTES
                    or not isinstance(meta.get('sha256'), str)
                    or not re.fullmatch('[0-9a-f]{64}', meta['sha256'])
                    or not isinstance(meta.get('name'), str)
                    or not meta['name'] or len(meta['name']) > 240
                    or any(ord(c) < 32 or c in '/\\' for c in meta['name'])
                    or type(meta.get('created')) not in (int, float)
                    or not 0 <= time.time() - meta['created'] < TTL):
                raise ValueError()
            if meta.get('complete') is not True:
                content = directory / 'content'
                info = content.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size != meta['size']:
                    raise ValueError()
            return meta
        except (OSError, ValueError, TypeError, RecursionError, KeyError):
            raise OutboxError('Transfer unavailable') from None

    @staticmethod
    def _public(meta):
        return {key: meta[key] for key in ('id', 'name', 'size', 'sha256')}

    def pending(self):
        with _LOCK:
            if not self.root.exists():
                return []
            result = []
            for directory in self.root.iterdir():
                try:
                    meta = self._load(directory.name)
                    if meta.get('complete') is not True:
                        result.append(self._public(meta))
                except OutboxError:
                    continue
            return result[:MAX_ITEMS]

    @staticmethod
    def _save(directory, meta):
        temp = directory / 'metadata.tmp'
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(meta, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, directory / 'metadata.json')

    def cleanup(self):
        """Remove only expired, validated local transfer directories."""
        with _LOCK:
            if not self.root.exists() or self.root.is_symlink():
                return
            for directory in self.root.iterdir():
                try:
                    self._directory(directory.name)
                    info = directory.lstat()
                    if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                        continue
                    path = directory / 'metadata.json'
                    if path.is_symlink() or path.stat().st_size > 4096:
                        continue
                    meta = json.loads(path.read_text(encoding='utf-8'))
                    if (isinstance(meta, dict) and meta.get('id') == directory.name
                            and type(meta.get('created')) in (int, float)
                            and time.time() - meta['created'] >= TTL):
                        shutil.rmtree(directory)
                except (OSError, ValueError, TypeError, RecursionError):
                    continue

    def enqueue(self, source, *, progress=None, cancelled=None):
        """Called only by the local desktop picker; paths never accepted over HTTP."""
        source = Path(source)
        # Serialise reservations, not long disk copies: existing downloads stay responsive.
        with _STAGE_LOCK:
            directory = None
            try:
                info = source.lstat()
                if (not stat.S_ISREG(info.st_mode) or source.is_symlink()
                        or getattr(info, 'st_file_attributes', 0) & 0x400
                        or str(source).startswith(('\\\\', '//'))
                        or info.st_size > MAX_BYTES or len(source.name) > 240):
                    raise OutboxError('Choose an existing local regular file, up to 50 GiB')
                self.root.mkdir(parents=True, exist_ok=True)
                if self.root.is_symlink():
                    raise OutboxError('Invalid transfer storage')
                self.cleanup()
                if len(self.pending()) >= MAX_ITEMS:
                    raise OutboxError('Outgoing queue is full')
                if shutil.disk_usage(self.root).free < info.st_size + 16 * 1024**2:
                    raise OutboxError('Not enough disk space to stage transfer')
                ident = uuid.uuid4().hex
                directory = self.root / ident
                directory.mkdir()
                digest = hashlib.sha256()
                size = 0
                with source.open('rb') as src, (directory / 'content').open('xb') as dst:
                    opened = os.fstat(src.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise OutboxError('Source changed; select it again')
                    while True:
                        if cancelled is not None and cancelled():
                            raise OutboxError('Staging canceled')
                        block = src.read(CHUNK_BYTES)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_BYTES:
                            raise OutboxError('File exceeds 50 GiB')
                        digest.update(block)
                        dst.write(block)
                        if progress is not None:
                            progress(size, info.st_size)
                    after = os.fstat(src.fileno())
                    if size != info.st_size or after.st_mtime_ns != opened.st_mtime_ns:
                        raise OutboxError('Source changed during staging')
                    dst.flush()
                    os.fsync(dst.fileno())
                meta = dict(id=ident, name=source.name, size=size,
                            sha256=digest.hexdigest(), created=time.time(), complete=False)
                self._save(directory, meta)
                return self._public(meta)
            except (OSError, OutboxError) as error:
                if directory is not None:
                    shutil.rmtree(directory, ignore_errors=True)
                if isinstance(error, OutboxError):
                    raise
                raise OutboxError('Cannot stage selected file') from None

    def chunk(self, ident, offset):
        with _LOCK:
            meta = self._load(ident)
            if (meta.get('complete') is True or type(offset) is not int or offset < 0
                    or offset % CHUNK_BYTES or offset >= meta['size'] and not (offset == meta['size'] == 0)):
                raise OutboxError('Invalid transfer offset')
            with (self._directory(ident) / 'content').open('rb') as stream:
                stream.seek(offset)
                return stream.read(min(CHUNK_BYTES, meta['size'] - offset))

    def ack(self, ident, sha256):
        with _LOCK:
            meta = self._load(ident)
            if sha256 != meta['sha256']:
                raise OutboxError('Digest mismatch')
            directory = self._directory(ident)
            meta['complete'] = True
            self._save(directory, meta)
            (directory / 'content').unlink(missing_ok=True)

    def discard(self, ident):
        with _LOCK:
            self._load(ident)
            shutil.rmtree(self._directory(ident))
