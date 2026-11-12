"""Explicit local-approved pairing. This module never starts a production server on import."""
import hmac
import datetime
import hashlib
import http.server
import json
import os
import pathlib
import socketserver
import ssl
import ipaddress
import math
import re
import secrets
import threading
import time
from urllib.parse import urlencode


class PairingError(Exception):
    def __init__(self, status, message='Pairing request unavailable'):
        super().__init__(message)
        self.status = status


class PairingSession:
    def __init__(self, key: str, host: str, mac: str = '', broadcast: str = '',
                 http_port: int = 8765, ttl=120, clock=time.monotonic):
        address = ipaddress.IPv4Address(host)
        if address.is_unspecified or address.is_multicast or not key or not 0 < ttl <= 120:
            raise ValueError('Invalid pairing configuration')
        if not 1 <= http_port <= 65535:
            raise ValueError('Invalid HTTP port')
        self._key, self._host = key, str(address)
        self._mac, self._broadcast, self._http_port = mac, broadcast, http_port
        self._clock, self._deadline = clock, clock() + ttl
        self._lock = threading.RLock()
        self._state = 'open'
        self._ticket = secrets.token_urlsafe(32)
        self._request_id = self._secret = self._name = self._code = ''

    def _expire(self):
        if self._clock() >= self._deadline and self._state not in ('consumed', 'rejected', 'expired'):
            self._state = 'expired'
            self._ticket = self._secret = self._key = ''

    def bootstrap_link(self, port=8767, fingerprint: str = ''):
        with self._lock:
            self._expire()
            if not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', fingerprint) or port != 8767:
                raise PairingError(400)
            if self._state != 'open':
                raise PairingError(410)
            return 'pcmote://pair?' + urlencode(dict(v=1, host=self._host, port=port,
                                                      fp=fingerprint, ticket=self._ticket))

    def claim(self, ticket, device_name):
        with self._lock:
            self._expire()
            if self._state != 'open':
                raise PairingError(410)
            if not isinstance(ticket, str) or not hmac.compare_digest(ticket.encode('utf-8'), self._ticket.encode('ascii')):
                raise PairingError(403)
            if not isinstance(device_name, str) or not 1 <= len(device_name.strip()) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in device_name):
                raise PairingError(400)
            self._ticket = ''
            self._request_id, self._secret = secrets.token_urlsafe(16), secrets.token_urlsafe(32)
            self._name = device_name.strip()
            self._code = '%06d' % secrets.randbelow(1000000)
            self._state = 'pending'
            return dict(v=1, state='pending', request_id=self._request_id,
                        session_secret=self._secret, confirm_code=self._code,
                        expires_in=self._remaining())

    def _remaining(self):
        return max(0, math.ceil(self._deadline - self._clock()))

    def _authenticate(self, request_id, session_secret):
        self._expire()
        # Terminal states deliberately disclose no credentials or key material.
        if self._state in ('expired', 'consumed', 'rejected'):
            raise PairingError(410)
        if not isinstance(request_id, str) or not isinstance(session_secret, str) or not self._secret:
            raise PairingError(403)
        if not (hmac.compare_digest(request_id.encode('utf-8'), self._request_id.encode('ascii'))
                and hmac.compare_digest(session_secret.encode('utf-8'), self._secret.encode('ascii'))):
            raise PairingError(403)

    def status(self, request_id, session_secret):
        with self._lock:
            self._authenticate(request_id, session_secret)
            result = dict(v=1, state=self._state, expires_in=self._remaining())
            if self._state == 'approved':
                result.update(pc_name='VzaimoPult', host=self._host, http_port=self._http_port,
                              discovery_port=8766, key=self._key)
                if self._mac:
                    result['mac'] = self._mac
                if self._broadcast:
                    result['broadcast'] = self._broadcast
            return result

    def ack(self, request_id, session_secret):
        with self._lock:
            self._authenticate(request_id, session_secret)
            if self._state != 'approved':
                raise PairingError(409)
            self._state = 'consumed'
            self._ticket = self._secret = self._key = ''

    def approve(self):
        with self._lock:
            self._expire()
            if self._state != 'pending':
                return False
            self._state = 'approved'
            return True

    def reject(self):
        with self._lock:
            self._expire()
            if self._state not in ('open', 'pending', 'approved'):
                return False
            self._state = 'rejected'
            self._ticket = self._secret = self._key = ''
            return True

    def snapshot(self):
        """Local UI only; intentionally excludes ticket, key and session secret."""
        with self._lock:
            self._expire()
            return dict(state=self._state, device_name=self._name,
                        confirm_code=self._code, expires_in=self._remaining())


def _protect(path, directory=False):
    """Fail closed if private-key storage cannot be restricted to this user."""
    if os.name != 'nt':
        os.chmod(path, 0o700 if directory else 0o600)
        return
    import csv
    import ctypes
    from ctypes import wintypes
    import subprocess
    executable = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'whoami.exe')
    result = subprocess.run([executable, '/user', '/fo', 'csv', '/nh'], capture_output=True,
                            text=True, check=True, creationflags=0x08000000)
    sid = list(csv.reader(result.stdout.splitlines()))[0][-1]
    if not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise RuntimeError('Cannot identify private-key owner')
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    apply = advapi.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    apply.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    inheritance = 'OICI' if directory else ''
    if not convert('D:P(A;%s;FA;;;%s)' % (inheritance, sid), 1, ctypes.byref(descriptor), None):
        raise RuntimeError('Cannot protect pairing TLS storage')
    try:
        if not apply(str(path), 0x80000004, descriptor):  # protected DACL + DACL_SECURITY_INFORMATION
            raise RuntimeError('Cannot protect pairing TLS storage')
    finally:
        kernel.LocalFree(descriptor)


def _certificate(data_dir, host):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    directory = pathlib.Path(data_dir) / 'pairing-tls'
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or (os.name == 'nt' and os.path.isjunction(directory)):
        raise RuntimeError('Unsafe pairing TLS directory')
    _protect(directory, directory=True)
    key_path, cert_path = directory / 'private.pem', directory / 'certificate.pem'
    for path in (key_path, cert_path):
        if path.is_symlink():
            raise RuntimeError('Unsafe pairing TLS file')
    if key_path.exists() != cert_path.exists():
        raise RuntimeError('Incomplete pairing TLS identity')
    if not key_path.exists():
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'VzaimoPult')])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(private.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - datetime.timedelta(days=1))
                       .not_valid_after(now + datetime.timedelta(days=3650))
                       .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), critical=False)
                       .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                       .sign(private, hashes.SHA256()))
        # The protected directory is secured before any key material is created.
        for path, content in ((key_path, private.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
                              (cert_path, certificate.public_bytes(serialization.Encoding.PEM))):
            with open(path, 'xb') as stream:
                stream.write(content)
            _protect(path)
    else:
        _protect(key_path)
        _protect(cert_path)
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return key_path, cert_path, certificate.fingerprint(hashes.SHA256()).hex()


class _BoundedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, context, session):
        self.context, self.session = context, session
        self.slots = threading.BoundedSemaphore(4)
        self.rate_lock = threading.Lock()
        self.rate_start, self.rate_count = time.monotonic(), 0
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(5)
            # Handshake runs in bounded worker, never the accept loop.
            with self.context.wrap_socket(request, server_side=True) as secured:
                super().process_request_thread(secured, client_address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never print request URLs, bodies, secrets, or attacker input.

    def allowed(self):
        with self.rate_lock:
            now = time.monotonic()
            if now - self.rate_start >= 60:
                self.rate_start, self.rate_count = now, 0
            self.rate_count += 1
            return self.rate_count <= 30


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'Pairing'
    sys_version = ''

    def log_message(self, format, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self._reply(code, {'error': 'Pairing request unavailable'})

    def _reply(self, code, body=None):
        raw = b'' if body is None else json.dumps(body, ensure_ascii=True).encode('ascii')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def do_GET(self):
        self._reply(405, {'error': 'POST required'})

    do_HEAD = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = do_GET

    def do_POST(self):
        try:
            if not self.server.allowed():
                raise PairingError(429)
            methods = {'/pair/v1/claim': ('ticket', 'device_name'),
                       '/pair/v1/status': ('request_id', 'session_secret'),
                       '/pair/v1/ack': ('request_id', 'session_secret')}
            if self.path not in methods:
                raise PairingError(404)
            if self.headers.get_all('Transfer-Encoding'):
                raise PairingError(400)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not re.fullmatch('[0-9]{1,10}', lengths[0]):
                raise PairingError(400)
            length = int(lengths[0])
            if length > 4096:
                raise PairingError(413)
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise PairingError(415)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise PairingError(400)
            data = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
            fields = methods[self.path]
            if not isinstance(data, dict) or set(data) != set(fields) or any(not isinstance(data[k], str) for k in fields):
                raise PairingError(400)
            action = self.path.rsplit('/', 1)[1]
            result = getattr(self.server.session, action)(*[data[k] for k in fields])
            self._reply(204 if action == 'ack' else 200, result)
        except PairingError as error:
            self._reply(error.status, {'error': 'Pairing request unavailable'})
        except (ValueError, UnicodeError, RecursionError):
            self._reply(400, {'error': 'Malformed request'})


class PairingServer:
    def __init__(self, session, data_dir, bind='0.0.0.0', port=8767):
        self.session, self.data_dir, self.bind, self.port = session, data_dir, bind, port
        self.fingerprint = ''
        self._server = self._thread = None

    def start(self):
        if self._server is not None:
            raise RuntimeError('Pairing server already started')
        key, cert, fingerprint = _certificate(self.data_dir, self.session._host)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(cert), str(key))
        server = _BoundedServer((self.bind, self.port), _Handler, context, self.session)
        self._server = server
        self.port, self.fingerprint = server.server_address[1], fingerprint
        self._thread = threading.Thread(target=server.serve_forever,
                                        kwargs={'poll_interval': 0.1}, name='pairing-https', daemon=True)
        self._thread.start()
        return self

    def close(self):
        server, thread = self._server, self._thread
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join(timeout=6)
            self._server = self._thread = None
