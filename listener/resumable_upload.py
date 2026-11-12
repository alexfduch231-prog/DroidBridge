"""Authenticated, durable resumable uploads; standard library only.

Root integration: call handle_resumable(handler) for POST /upload/resume/*.
State is authenticated with the existing bearer key, never stores that key,
and never accepts paths from the network. One listener process owns its index.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
import time
from urllib.parse import quote, urlparse

if __package__:
    from .file_upload import _filename
    from .upload_settings import upload_directory
else:
    from file_upload import _filename
    from upload_settings import upload_directory

CHUNK_BYTES = 4 * 1024**2
MAX_BYTES = 50 * 1024**3
MAX_SESSIONS = 32
TTL = 7 * 86400
_SLOTS = threading.BoundedSemaphore(2)
_CATALOG = threading.RLock()
_LOCKS = [threading.RLock() for _ in range(64)]
_ID = re.compile(r'[0-9a-f]{32}')
_HASH = re.compile(r'[0-9a-f]{64}')


class ProtocolError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def _error(status, message):
    raise ProtocolError(status, message)


def _valid_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _error(400, 'Invalid upload id')
    return value


def _name(value):
    if not isinstance(value, str):
        raise ValueError('Invalid filename')
    # _filename decodes percent escapes once; JSON names are already raw Unicode.
    return _filename(quote(value, safe=''))


def _safe(path, directory=False):
    """Reject symlinks, Windows junctions/reparse points, and wrong file types."""
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise OSError('Unsafe upload state')
    return info


def _ancestors(path):
    for item in (path, *path.parents):
        _safe(item, directory=True)


def _sync_dir(path):
    # Windows fsync on a directory is not supported by Python. File contents and
    # replace are flushed; POSIX also needs directory fsync for rename durability.
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _canonical(state):
    return json.dumps(state, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def _save(index, state, token):
    raw = _canonical(state)
    payload = _canonical({'state': state, 'mac': hmac.new(token.encode(), raw, hashlib.sha256).hexdigest()})
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=index, prefix='.index-', delete=False) as out:
            temp = Path(out.name)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        destination = index / (state['id'] + '.json')
        if destination.exists() or destination.is_symlink():
            _safe(destination)
        os.replace(temp, destination)
        temp = None
        _sync_dir(index)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _load(index, ident, token):
    path = index / (ident + '.json')
    try:
        _safe(path)
    except FileNotFoundError:
        return None
    with path.open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise OSError('Invalid upload state')
    try:
        envelope = json.loads(raw, object_pairs_hook=_pairs)
        state = envelope['state']
        mac = hmac.new(token.encode(), _canonical(state), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(envelope['mac'], mac):
            raise ValueError('Invalid signature')
        required = {'id','name','size','sha256','root','offset','updated','complete','target'}
        if set(state) != required or state['id'] != ident:
            raise ValueError('Invalid state')
        _valid_id(ident)
        _name(state['name'])
        if (type(state['size']) is not int or not 0 <= state['size'] <= MAX_BYTES
                or type(state['offset']) is not int or not 0 <= state['offset'] <= state['size']
                or (state['offset'] != state['size'] and state['offset'] % CHUNK_BYTES)
                or not _HASH.fullmatch(state['sha256'])
                or type(state['complete']) is not bool
                or type(state['updated']) not in (int, float)
                or not isinstance(state['root'], str) or not Path(state['root']).is_absolute()
                or (state['target'] is not None and _name(state['target']) != state['target'])
                or (state['complete'] and (not state['target'] or state['offset'] != state['size']))):
            raise ValueError('Invalid state')
        return state
    except (KeyError, TypeError, ValueError, RecursionError):
        raise OSError('Invalid upload state') from None


def _paths(state):
    root = Path(state['root'])
    _ancestors(root)
    folder = root / ('.pcmote-resume-' + state['id'])
    _safe(folder, directory=True)
    return root, folder, folder / 'data.part'


def _delete(index, state):
    # Only exact owned paths, never recursive deletion and never final targets.
    root = Path(state['root'])
    _ancestors(root)
    folder = root / ('.pcmote-resume-' + state['id'])
    if folder.exists() or folder.is_symlink():
        _safe(folder, directory=True)
        part = folder / 'data.part'
        if part.exists() or part.is_symlink():
            _safe(part)
            part.unlink()
        folder.rmdir()
        _sync_dir(root)
    (index / (state['id'] + '.json')).unlink(missing_ok=True)
    _sync_dir(index)


def _recover(state):
    root = Path(state['root'])
    _ancestors(root)
    folder = root / ('.pcmote-resume-' + state['id'])
    # A durable zero-offset index is also the creation intent. Recover crashes
    # between index, directory, and empty-part creation without trusting orphans.
    if not state['complete'] and state['offset'] == 0 and state['target'] is None:
        if not folder.exists() and not folder.is_symlink():
            folder.mkdir()
            _sync_dir(root)
        _safe(folder, directory=True)
        candidate = folder / 'data.part'
        if not candidate.exists() and not candidate.is_symlink():
            with candidate.open('xb') as out:
                out.flush()
                os.fsync(out.fileno())
            _sync_dir(folder)
    _, _, part = _paths(state)
    if state['complete']:
        return
    info = _safe(part)
    if info.st_size < state['offset']:
        raise OSError('Committed data missing')
    if info.st_size > state['offset']:
        with part.open('r+b') as out:
            out.truncate(state['offset'])
            out.flush()
            os.fsync(out.fileno())


def _result(state):
    result = {key:state[key] for key in ('id','offset','size','complete')}
    result['ok'] = True
    if state['complete']:
        result.update(name=state['target'], path=str(Path(state['root']) / state['target']))
    return result


def _index(server):
    data = Path(getattr(server, 'upload_data_dir', None)
                or os.environ.get('VZAIMOPULT_DATA_DIR') or Path(__file__).parent)
    data = data.absolute()
    data.mkdir(parents=True, exist_ok=True)
    _ancestors(data)
    index = data / 'resumable-uploads'
    index.mkdir(exist_ok=True)
    _safe(index, directory=True)
    return index


def _length(handler, limit):
    if handler.headers.get('Transfer-Encoding'):
        _error(400, 'Content-Length required; Transfer-Encoding forbidden')
    lengths = handler.headers.get_all('Content-Length', [])
    if not lengths:
        _error(411, 'Content-Length required')
    if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,20}', lengths[0]):
        _error(400, 'Invalid Content-Length')
    value = int(lengths[0])
    if value > limit:
        _error(413, 'Request too large')
    return value


def _read(handler, length):
    body = bytearray()
    while len(body) < length:
        block = handler.rfile.read(min(256 * 1024, length - len(body)))
        if not block:
            _error(400, 'Interrupted request')
        body.extend(block)
    return bytes(body)


def _create(index, value, server, token):
    if set(value) != {'id','name','size','sha256'}:
        _error(400, 'Invalid create fields')
    name = _name(value['name'])
    size = value['size']
    if type(size) is not int or size < 0:
        _error(400, 'Invalid size')
    if size > MAX_BYTES:
        _error(413, 'Maximum file size is 50 GiB')
    if not isinstance(value['sha256'], str) or not _HASH.fullmatch(value['sha256']):
        _error(400, 'Invalid SHA256')
    ident = value['id']
    with _CATALOG:
        existing = _load(index, ident, token)
        if existing is not None:
            if time.time() - existing['updated'] <= TTL:
                if any(existing[k] != value[k] for k in ('name','size','sha256')):
                    _error(409, 'Upload identity changed')
                _recover(existing)
                return 200, _result(existing)
            _delete(index, existing)
        sessions = []
        for entry in index.iterdir():
            if entry.suffix != '.json':
                continue
            if not _ID.fullmatch(entry.stem):
                raise OSError('Invalid index entry')
            state = _load(index, entry.stem, token)
            if state is None:
                continue
            # Expiry cleanup must not race an active upload on another stripe.
            lock = _LOCKS[int(entry.stem[:2], 16) % len(_LOCKS)]
            if time.time()-state['updated'] > TTL and lock.acquire(blocking=False):
                try:
                    state = _load(index, entry.stem, token)
                    if state is not None and time.time()-state['updated'] > TTL:
                        _delete(index, state)
                        continue
                finally:
                    lock.release()
            sessions.append(state)
        if len(sessions) >= MAX_SESSIONS:
            _error(429, 'Too many upload sessions')
        override = getattr(server, 'downloads_dir', None)
        root = Path(override) if override is not None else upload_directory(index.parent)
        root = root.absolute()
        _ancestors(root)
        # Reserve all remaining bytes, not just this request, against free space.
        device = root.stat().st_dev
        reserved = sum(s['size']-s['offset'] for s in sessions
                       if not s['complete'] and Path(s['root']).stat().st_dev == device)
        if shutil.disk_usage(root).free < size + reserved + 16 * 1024**2:
            _error(507, 'Insufficient disk space')
        # Recovery requires an atomic no-clobber hard link, unavailable on FAT /
        # exFAT. Fail before accepting the session rather than after its transfer.
        probe = None
        linked = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, prefix='.pcmote-probe-', delete=False) as out:
                probe = Path(out.name)
            linked = probe.with_name(probe.name + '.link')
            os.link(probe, linked)
        except OSError:
            _error(500, 'Для возобновляемой передачи выбери папку на диске с поддержкой жёстких ссылок (например NTFS)')
        finally:
            if linked is not None:
                linked.unlink(missing_ok=True)
            if probe is not None:
                probe.unlink(missing_ok=True)
        folder = root / ('.pcmote-resume-' + ident)
        if folder.exists() or folder.is_symlink():
            raise OSError('Unindexed upload folder')
        state = dict(value, root=str(root), offset=0, updated=time.time(), complete=False, target=None)
        _save(index, state, token)
        _recover(state)
        return 201, _result(state)


def _finish(index, state, token):
    if state['complete']:
        return
    if state['offset'] != state['size']:
        _error(409, 'Upload incomplete')
    root, folder, part = _paths(state)
    digest = hashlib.sha256()
    with part.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    if not hmac.compare_digest(digest.hexdigest(), state['sha256']):
        _error(409, 'File SHA256 mismatch')
    stem, suffix = os.path.splitext(state['name'])
    for number in range(10000):
        if state['target'] is None:
            if number == 0:
                state['target'] = state['name']
            else:
                tail = ' (%d)%s' % (number, suffix)
                prefix = stem
                # Keep generated names inside the same persisted filename policy.
                # A long extension is shortened too if no stem budget remains.
                while len((prefix + tail).encode('utf-16-le')) > 360:
                    if prefix:
                        prefix = prefix[:-1]
                    else:
                        tail = tail[:-1]
                state['target'] = _name(prefix + tail)
            # Durable intent BEFORE publishing; part remains as an identity witness.
            _save(index, state, token)
        target = root / state['target']
        try:
            if target.exists() or target.is_symlink():
                try:
                    _safe(target)
                except OSError:
                    # Directories, links and reparse points are occupied names,
                    # not destinations to follow, overwrite, or remove.
                    state['target'] = None
                    continue
                if os.path.samefile(part, target):
                    break
                state['target'] = None
                continue
            # Atomic no-clobber publication. Keep part until receipt is durable.
            os.link(part, target)
            _sync_dir(root)
            break
        except FileExistsError:
            state['target'] = None
    else:
        raise OSError('Too many filename collisions')
    state['complete'] = True
    state['updated'] = time.time()
    _save(index, state, token)
    # Retain the private link as crash/recovery witness until TTL/abort. It shares
    # storage with the final file and cleanup never deletes the final pathname.


def handle_resumable(handler):
    """Handle POST /upload/resume/{create,status,chunk,finish,abort}."""
    acquired = False
    try:
        token = getattr(handler.server, 'token', '')
        expected = ('Bearer ' + token).encode('utf-8')
        actual = handler.headers.get('Authorization', '').encode('utf-8')
        if not token or not hmac.compare_digest(actual, expected):
            _error(403, 'Invalid bearer key')
        action = urlparse(handler.path).path.removeprefix('/upload/resume/')
        if action not in ('create','status','chunk','finish','abort'):
            _error(404, 'Route not found')
        length = _length(handler, CHUNK_BYTES if action == 'chunk' else 8192)
        acquired = _SLOTS.acquire(blocking=False)
        if not acquired:
            _error(429, 'Two uploads already active; retry later')
        handler.connection.settimeout(60)
        if action == 'chunk':
            ident = _valid_id(handler.headers.get('X-Upload-Id'))
            offset = handler.headers.get('X-Upload-Offset', '')
            checksum = handler.headers.get('X-Chunk-SHA256', '')
            if not re.fullmatch(r'[0-9]{1,20}', offset) or not _HASH.fullmatch(checksum):
                _error(400, 'Invalid chunk headers')
            offset = int(offset)
        else:
            value = json.loads(_read(handler, length).decode('utf-8'), object_pairs_hook=_pairs)
            if not isinstance(value, dict):
                _error(400, 'JSON object required')
            ident = _valid_id(value.get('id'))
            if action != 'create' and set(value) != {'id'}:
                _error(400, 'Invalid request fields')
        index = _index(handler.server)
        lock = _LOCKS[int(ident[:2], 16) % len(_LOCKS)]
        with lock:
            if action == 'create':
                status, result = _create(index, value, handler.server, token)
            else:
                state = _load(index, ident, token)
                if state is None:
                    _error(404, 'Upload not found or expired')
                if time.time()-state['updated'] > TTL:
                    _delete(index, state)
                    _error(404, 'Upload not found or expired')
                if action == 'abort':
                    _delete(index, state)
                    result = {'ok': True, 'id': ident}
                elif action == 'chunk':
                    _recover(state)
                    if (state['complete'] or offset != state['offset']
                            or not length or length != min(CHUNK_BYTES, state['size']-offset)):
                        _error(409, 'Chunk offset or length conflict; query status')
                    # Buffer at most one bounded chunk; interrupted/hash-invalid
                    # requests never touch the committed part at all.
                    body = _read(handler, length)
                    if not hmac.compare_digest(hashlib.sha256(body).hexdigest(), checksum):
                        _error(409, 'Chunk SHA256 mismatch')
                    _, _, part = _paths(state)
                    _safe(part)
                    with part.open('r+b') as out:
                        out.seek(offset)
                        out.write(body)
                        out.flush()
                        os.fsync(out.fileno())
                    state['offset'] += length
                    state['updated'] = time.time()
                    _save(index, state, token)
                    result = _result(state)
                else:
                    _recover(state)
                    if action == 'finish':
                        _finish(index, state, token)
                    else:
                        state['updated'] = time.time()
                        _save(index, state, token)
                    result = _result(state)
                status = 200
        _reply(handler, status, result)
    except ProtocolError as exc:
        _reply(handler, exc.status, {'ok': False, 'error': exc.message})
    except (ValueError, UnicodeError, RecursionError):
        _reply(handler, 400, {'ok': False, 'error': 'Invalid request'})
    except TimeoutError:
        _reply(handler, 408, {'ok': False, 'error': 'Upload timed out'})
    except OSError:
        _reply(handler, 500, {'ok': False, 'error': 'Upload storage unavailable'})
    finally:
        if acquired:
            _SLOTS.release()


def _reply(handler, status, payload):
    handler.close_connection = True
    try:
        handler.send_bytes(status, 'application/json; charset=utf-8',
                           json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    except OSError:
        pass  # A lost response is recovered through status/create/finish.
