"""Pairing security contract. No production listener is started by these tests."""
import concurrent.futures
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

from pairing import PairingError, PairingSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.session = PairingSession('test-existing-key', '192.168.1.20',
                                     mac='AA:BB:CC:DD:EE:FF', clock=lambda: self.now)
        self.ticket = parse_qs(urlsplit(self.session.bootstrap_link(
            fingerprint='a' * 64)).query)['ticket'][0]

    def claim(self):
        return self.session.claim(self.ticket, 'Phone')

    def status(self, claim):
        return self.session.status(claim['request_id'], claim['session_secret'])

    def error(self, code, fn, *args):
        with self.assertRaises(PairingError) as caught:
            fn(*args)
        self.assertEqual(code, caught.exception.status)
        self.assertNotIn('test-existing-key', str(caught.exception))

    def test_credentials_only_after_local_approval_and_retry_until_ack(self):
        claim = self.claim()
        self.assertEqual('pending', self.status(claim)['state'])
        self.assertNotIn('key', claim)
        self.assertNotIn('key', self.status(claim))
        self.assertTrue(self.session.approve())
        approved = self.status(claim)
        self.assertEqual('test-existing-key', approved['key'])
        self.assertEqual(8765, approved['http_port'])
        self.assertEqual(approved, self.status(claim))
        self.session.ack(claim['request_id'], claim['session_secret'])
        self.error(410, self.session.status, claim['request_id'], claim['session_secret'])
        self.error(410, self.session.claim, self.ticket, 'Phone')

    def test_ticket_claim_is_atomic(self):
        def attempt(_):
            try:
                return self.claim()['state']
            except PairingError:
                return 'denied'
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(attempt, range(24)))
        self.assertEqual(1, results.count('pending'))

    def test_expiry_covers_approved_and_local_ui(self):
        claim = self.claim()
        self.session.approve()
        self.now = 220.0
        self.error(410, self.session.status, claim['request_id'], claim['session_secret'])
        self.assertEqual('expired', self.session.snapshot()['state'])
        self.assertFalse(self.session.approve())

    def test_wrong_credentials_and_reject(self):
        self.error(403, self.session.claim, 'bad', 'Phone')
        claim = self.claim()
        self.error(403, self.session.status, claim['request_id'], 'bad')
        self.error(403, self.session.ack, 'bad', claim['session_secret'])
        self.assertTrue(self.session.reject())
        self.error(410, self.session.status, claim['request_id'], claim['session_secret'])

    def test_local_cancel_also_revokes_an_approved_but_unconsumed_session(self):
        claim = self.claim()
        self.session.approve()
        self.assertTrue(self.session.reject())
        self.error(410, self.session.status, claim['request_id'], claim['session_secret'])

    def test_ack_requires_approval(self):
        claim = self.claim()
        self.error(409, self.session.ack, claim['request_id'], claim['session_secret'])
        self.assertTrue(self.session.approve())

    def test_ui_snapshot_never_exposes_credentials(self):
        self.assertFalse(self.session.approve())
        claim = self.claim()
        view = self.session.snapshot()
        self.assertEqual(claim['confirm_code'], view['confirm_code'])
        self.assertEqual('Phone', view['device_name'])
        for secret in ('test-existing-key', self.ticket, claim['session_secret']):
            self.assertNotIn(secret, repr(view))

    def test_malformed_name_and_bootstrap_rejected(self):
        self.error(400, self.session.claim, self.ticket, '\nspoof')
        self.error(400, self.session.claim, self.ticket, 'x' * 81)
        self.error(400, self.session.bootstrap_link, 8767, 'wrong')


class ServerTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pairing import PairingServer
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session = PairingSession('network-test-key', '192.168.1.20')
        self.server = PairingServer(self.session, self.directory.name, bind='127.0.0.1', port=0)
        self.server.start()
        self.addCleanup(self.server.close)

    def request(self, path, body=b'{}', method='POST', headers=None):
        import http.client
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Tests verify DER pin independently below.
        client = http.client.HTTPSConnection('127.0.0.1', self.server.port, context=context, timeout=5)
        try:
            client.request(method, path, body, headers or {'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            client.close()

    def test_network_cannot_approve_and_key_stays_hidden_until_local_approval(self):
        import json
        ticket = parse_qs(urlsplit(self.session.bootstrap_link(fingerprint=self.server.fingerprint)).query)['ticket'][0]
        code, raw, headers = self.request('/pair/v1/claim', json.dumps({'ticket': ticket, 'device_name': 'Phone'}).encode())
        self.assertEqual(200, code)
        self.assertEqual('no-store', headers['Cache-Control'])
        claim = json.loads(raw)
        auth = json.dumps({k: claim[k] for k in ('request_id', 'session_secret')}).encode()
        self.assertNotIn(b'network-test-key', raw)
        self.assertEqual(404, self.request('/pair/v1/approve')[0])
        self.assertNotIn(b'network-test-key', self.request('/pair/v1/status', auth)[1])
        self.session.approve()
        self.assertIn(b'network-test-key', self.request('/pair/v1/status', auth)[1])
        self.assertEqual(204, self.request('/pair/v1/ack', auth)[0])
        self.assertEqual(410, self.request('/pair/v1/status', auth)[0])

    def test_http_bounds_methods_paths_and_json(self):
        for path, body, method, expected in [
            ('/pair/v1/claim', b'x' * 4097, 'POST', 413),
            ('/pair/v1/status', b'[]', 'POST', 400),
            ('/pair/v1/status', b'{bad', 'POST', 400),
            ('/pair/v1/status', b'{"request_id":"x","request_id":"y"}', 'POST', 400),
            ('/pair/v1/status?ticket=secret', b'{}', 'POST', 404),
            ('/pair/v1/claim', b'{}', 'GET', 405),
        ]:
            with self.subTest(expected=expected, path=path):
                self.assertEqual(expected, self.request(path, body, method)[0])
        self.assertEqual(415, self.request('/pair/v1/claim', headers={'Content-Type': 'text/plain'})[0])
        self.assertEqual(400, self.request('/pair/v1/claim', headers={'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked'})[0])

    def test_tls12_pin_and_persistent_certificate(self):
        import hashlib
        import socket
        import ssl
        from pairing import PairingServer
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
        with socket.create_connection(('127.0.0.1', self.server.port), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname='127.0.0.1') as tls:
                self.assertEqual(self.server.fingerprint, hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest())
        old = self.server.fingerprint
        self.server.close()
        server2 = PairingServer(self.session, self.directory.name, bind='127.0.0.1', port=0)
        server2.start()
        self.addCleanup(server2.close)
        self.assertEqual(old, server2.fingerprint)

    def test_four_stalled_handshakes_do_not_create_more_workers(self):
        import socket
        import time
        sockets = []
        try:
            for _ in range(4):
                sockets.append(socket.create_connection(('127.0.0.1', self.server.port), timeout=2))
            deadline = time.monotonic() + 2
            while self.server._server.slots._value != 0 and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(0, self.server._server.slots._value)
            with socket.create_connection(('127.0.0.1', self.server.port), timeout=2) as fifth:
                fifth.settimeout(2)
                self.assertEqual(b'', fifth.recv(1))
        finally:
            for sock in sockets:
                sock.close()

    def test_rate_limit(self):
        codes = [self.request('/pair/v1/status')[0] for _ in range(35)]
        self.assertIn(429, codes)


if __name__ == '__main__':
    unittest.main()
