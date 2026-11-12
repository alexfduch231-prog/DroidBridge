import http.client
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from urllib.parse import quote

spec = importlib.util.spec_from_file_location('pc_listener', Path(__file__).with_name('pc-listener.py'))
listener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(listener)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.server = listener.Server(('127.0.0.1', 0), listener.Handler)
        self.server.token = 'test-secret'
        self.server.downloads_dir = self.root
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def upload(self, body=b'hello', name='test.txt', token='test-secret', extra=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        headers = {'Authorization': 'Bearer ' + token, 'X-File-Name': quote(name, safe=''),
                   'Content-Type': 'application/octet-stream', 'Content-Length': str(len(body))}
        headers.update(extra or {})
        conn.request('POST', '/upload', body=body, headers=headers)
        response = conn.getresponse()
        status, data = response.status, response.read()
        conn.close()
        return status, json.loads(data) if data.startswith(b'{') else data

    def test_upload_with_isolated_python_path(self):
        import sys
        original = sys.path[:]
        previous = sys.modules.pop('file_upload', None)
        try:
            sys.path[:] = [p for p in sys.path if Path(p or '.').resolve() != Path(__file__).parent.resolve()]
            self.assertEqual(201, self.upload()[0])
        finally:
            sys.path[:] = original
            if previous is not None:
                sys.modules['file_upload'] = previous

    def test_unicode_upload_saves_exact_bytes(self):
        data = bytes(range(256)) * 1024
        status, result = self.upload(data, 'Фото с телефона.bin')
        self.assertEqual(201, status)
        self.assertTrue(result['ok'])
        self.assertEqual(len(data), result['size'])
        self.assertEqual(data, (self.root / result['name']).read_bytes())
        self.assertEqual('Фото с телефона.bin', result['name'])

    def test_wrong_key_does_not_create_files(self):
        self.assertEqual(403, self.upload(token='wrong')[0])
        self.assertEqual([], list(self.root.iterdir()))

    def test_duplicate_never_overwrites(self):
        self.assertEqual(201, self.upload(b'first')[0])
        status, result = self.upload(b'second')
        self.assertEqual(201, status)
        self.assertNotEqual('test.txt', result['name'])
        self.assertEqual(b'first', (self.root / 'test.txt').read_bytes())
        self.assertEqual(b'second', (self.root / result['name']).read_bytes())

    def test_unsafe_names_rejected(self):
        for name in ['../escape.txt', '..\\escape.txt', 'C:\\escape.txt', 'CON', 'NUL.txt',
                     'file:stream', 'bad\x00.txt', '.', 'trailing.', 'trailing ', 'a/b.txt']:
            with self.subTest(name=name):
                self.assertEqual(400, self.upload(name=name)[0])
        self.assertEqual([], list(self.root.iterdir()))

    def test_large_file_limit_50_gib(self):
        import file_upload
        from unittest.mock import patch, Mock
        self.assertEqual(50 * 1024**3, file_upload.MAX_BYTES)
        with patch.object(file_upload.shutil, 'disk_usage', return_value=Mock(free=0)):
            for size in (2 * 1024**3 + 1, 50 * 1024**3):
                self.assertEqual(507, self.upload(extra={'Content-Length': str(size)})[0])
        self.assertEqual(413,self.upload(extra={'Content-Length':str(50 * 1024**3 + 1)})[0])

    def test_invalid_lengths_and_encoding_rejected(self):
        for value, status in [('-1', 400), ('abc', 400), (str(50 * 1024**3 + 1), 413)]:
            self.assertEqual(status, self.upload(extra={'Content-Length': value})[0])
        self.assertEqual(400, self.upload(extra={'Transfer-Encoding': 'chunked'})[0])
        self.assertEqual([], list(self.root.iterdir()))

    def test_missing_length_rejected(self):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.putrequest('POST', '/upload')
        conn.putheader('Authorization', 'Bearer test-secret')
        conn.putheader('X-File-Name', 'test.txt')
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(411, response.status)
        response.read()
        conn.close()

    def test_empty_file_supported(self):
        status, result = self.upload(b'')
        self.assertEqual(201, status)
        self.assertEqual(b'', (self.root / result['name']).read_bytes())

    def test_truncated_upload_leaves_no_file(self):
        sock = socket.create_connection(self.server.server_address, timeout=3)
        sock.sendall(b'POST /upload HTTP/1.0\r\nAuthorization: Bearer test-secret\r\n'
                     b'X-File-Name: broken.bin\r\nContent-Length: 100\r\n\r\nshort')
        sock.shutdown(socket.SHUT_WR)
        reply = b''
        while True:
            part = sock.recv(4096)
            if not part:
                break
            reply += part
        sock.close()
        self.assertIn(b'400', reply.split(b'\r\n')[0])
        self.assertEqual([], list(self.root.iterdir()))


if __name__ == '__main__':
    unittest.main()
