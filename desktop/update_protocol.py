"""Pinned, offline-verifiable release protocol. Importing never accesses the network."""
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, unquote

CURRENT_VERSION = '1.0.9'
REPOSITORY = 'alexfduch231-prog/DroidBridge'
FEED_URL = 'https://github.com/' + REPOSITORY + '/releases/latest/download/update-manifest.json'
DOMAIN = b'DroidBridge/update-manifest/v1\n'
MAX_ENVELOPE = 64 * 1024
MAX_PAYLOAD = 32 * 1024
ALLOWED_HOSTS = frozenset(('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com', 'api.github.com'))
PUBLIC_KEY = 'MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuDbZDgHDC3XNP0eH2nQGxYD33yWhS6lgUZ2gVyNB+E6p4YArsY4XKKa2rT52IAZKJEhYlqd28bBncIzVJ4pK1OXl14qMs7HSgVZl52fIryE3g0vQUXE+dQ0Oa/5nKXxbFmD/r/VHBAnnJOZqoeNLVM+Prw3y9fUpxKCHVLAFjtySuF+ltVROTGUBTzF2ttO3NrSHOPBMBT778QwYg1bC/gj87boQYTRD/g/qUNweRLBy0qtsz52kg1A+gIEw2wzVyMDeyRTWRM9ooXS9Nxw5E0f9qwmkjeKSqwllazlBna34lY7RPl5h4LUzihzedJoV0hP1fPt79MemZOwviTpOHy4V3FSoCwpLL+b04VOqm//gG7oeBb1fIVCvzEy7mKc6ws+1OyxDXaVvMhMBhL/aK9A60z8g4qSEQzgXsJ0NPPl24XyH2T2NXza20CKjpSwNtt9mW7nCtqqq8gVNAb88i7X6zK0GMAOip9bPC+81Zz692r2exBehf8e59wEaGTszAgMBAAE='


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('invalid UTF-8 JSON') from error


def _der(data, offset=0):
    tag, length = data[offset], data[offset + 1]
    start = offset + 2
    if length & 128:
        count = length & 127
        length = int.from_bytes(data[start:start + count], 'big')
        start += count
    return tag, data[start:start + length], start + length


def _verify_signature(raw, signature):
    # Fixed trusted SPKI: extract the RSA public integers, then compare the entire
    # EMSA-PKCS1-v1_5 block, including all padding and the SHA256 DigestInfo.
    _, spki, _ = _der(base64.b64decode(PUBLIC_KEY))
    _, _, end = _der(spki)
    _, bits, _ = _der(spki, end)
    _, rsa, _ = _der(bits[1:])
    _, modulus, end = _der(rsa)
    _, exponent, _ = _der(rsa, end)
    n, e = int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big')
    if n.bit_length() != 3072 or len(signature) != 384 or int.from_bytes(signature, 'big') >= n:
        raise ValueError('invalid signature')
    digest = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(DOMAIN + raw).digest()
    expected = b'\x00\x01' + b'\xff' * (384 - len(digest) - 3) + b'\x00' + digest
    actual = pow(int.from_bytes(signature, 'big'), e, n).to_bytes(384, 'big')
    if not hmac.compare_digest(actual, expected):
        raise ValueError('invalid signature')


def validate_https_url(url):
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in url) or '\\' in url:
        raise ValueError('invalid URL')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc not in ALLOWED_HOSTS or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username is not None or parsed.password is not None or parsed.port is not None or parsed.fragment):
        raise ValueError('untrusted HTTPS URL')
    return parsed


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid integer')


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})', value):
        raise ValueError('invalid Windows version')
    numbers = tuple(map(int, value.split('.')))
    if any(n > 2147483647 for n in numbers):
        raise ValueError('version overflow')
    return numbers


def is_newer(candidate, installed=CURRENT_VERSION):
    return version_tuple(candidate) > version_tuple(installed)


def _time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise ValueError('invalid UTC timestamp')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def validate_payload(payload, *, now=None):
    if not isinstance(payload, dict) or type(payload.get('schema')) is not int or payload['schema'] != 1:
        raise ValueError('unsupported schema')
    if payload.get('repository') != REPOSITORY or payload.get('channel') != 'stable':
        raise ValueError('wrong repository or channel')
    _integer(payload.get('sequence'), 1, 9223372036854775807)
    published, expires = _time(payload.get('publishedAt')), _time(payload.get('expiresAt'))
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError('clock must be timezone aware')
    if expires <= published or expires <= now:
        raise ValueError('manifest expired')
    if published > now:
        raise ValueError('manifest published in future')
    for platform, limit, suffix in (('windows', 512 * 1024 * 1024, '.exe'), ('android', 128 * 1024 * 1024, '.apk')):
        item = payload.get(platform)
        if not isinstance(item, dict):
            raise ValueError('both platforms required')
        _integer(item.get('size'), 1, limit)
        if not isinstance(item.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
            raise ValueError('invalid hash')
        name = item.get('assetName')
        if not isinstance(name, str) or len(name) > 180 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name) or not name.endswith(suffix):
            raise ValueError('invalid asset name')
        parsed = validate_https_url(item.get('url'))
        prefix = '/' + REPOSITORY + '/releases/download/'
        if parsed.netloc != 'github.com' or parsed.query or not parsed.path.startswith(prefix):
            raise ValueError('wrong asset repository')
        pieces = parsed.path[len(prefix):].split('/')
        if len(pieces) != 2 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', pieces[0]) or pieces[1] != name:
            raise ValueError('invalid asset path')
        if platform == 'windows':
            version_tuple(item.get('version'))
            if item.get('architecture') != 'x64':
                raise ValueError('wrong architecture')
        else:
            if item.get('packageName') != 'ru.alexv.pcmote':
                raise ValueError('wrong Android package')
            _integer(item.get('versionCode'), 1, 2147483647)
            _integer(item.get('minSdk'), 21, 2147483647)
            if not isinstance(item.get('versionName'), str) or not 1 <= len(item['versionName']) <= 100:
                raise ValueError('invalid Android version')
            certs = item.get('signerCertSha256')
            if not isinstance(certs, list) or not 1 <= len(certs) <= 16 or any(not isinstance(c, str) or not re.fullmatch('[a-f0-9]{64}', c) for c in certs):
                raise ValueError('invalid signing certificate')
            if len(set(certs)) != len(certs):
                raise ValueError('duplicate signing certificate')
    return payload


def verify_manifest(envelope, *, now=None):
    if len(envelope) > MAX_ENVELOPE:
        raise ValueError('envelope too large')
    obj = strict_json(envelope)
    if not isinstance(obj, dict) or set(obj) != {'payload', 'signature'}:
        raise ValueError('invalid envelope')
    try:
        raw = base64.b64decode(obj['payload'], validate=True)
        signature = base64.b64decode(obj['signature'], validate=True)
    except (ValueError, TypeError, binascii.Error) as error:
        raise ValueError('invalid base64') from error
    if len(raw) > MAX_PAYLOAD:
        raise ValueError('payload too large')
    _verify_signature(raw, signature)
    return validate_payload(strict_json(raw), now=now)


class SequenceState:
    """Corrupt existing state fails closed. Only verified manifests call accept."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'update_state.json'

    def maximum(self):
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(1025)
        except FileNotFoundError:
            return 0
        if len(raw) > 1024:
            raise ValueError('state too large')
        obj = strict_json(raw)
        if not isinstance(obj, dict) or set(obj) != {'maxVerifiedSequence'}:
            raise ValueError('invalid update state')
        value = obj['maxVerifiedSequence']
        _integer(value, 1, 9223372036854775807)
        return value

    def accept(self, sequence):
        _integer(sequence, 1, 9223372036854775807)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Cross-process lock prevents two GUI checks from lowering the high-water mark.
        import msvcrt
        with (self.directory / 'update_state.lock').open('a+b') as lock:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                if sequence < self.maximum():
                    raise ValueError('manifest rollback')
                fd, temporary = tempfile.mkstemp(prefix='update-state-', suffix='.tmp', dir=self.directory)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(json.dumps({'maxVerifiedSequence': sequence}).encode('ascii'))
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, self.path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
