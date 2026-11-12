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
        from unittest.mock import patch
        import upload_settings
        self.default_patch = patch.object(upload_settings, 'downloads_folder', return_value=self.root / 'default-downloads')
        self.default_patch.start()
        self.addCleanup(self.default_patch.stop)
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

    def configured_destination(self):
        import upload_settings
        del self.server.downloads_dir
        self.server.upload_data_dir = self.root / 'data'
        folder = self.root / 'received'
        folder.mkdir()
        upload_settings.save_upload_directory(self.server.upload_data_dir, folder)
        return folder

    def test_request_cannot_choose_or_change_destination(self):
        folder = self.configured_destination()
        forbidden = self.root / 'remote-choice'
        status, _ = self.upload(b'{"directory":"remote-choice"}', extra={
            'X-Upload-Directory': str(forbidden), 'X-Download-Directory': str(forbidden)})
        self.assertEqual(status, 201)
        self.assertEqual((folder / 'test.txt').read_bytes(), b'{"directory":"remote-choice"}')
        self.assertFalse(forbidden.exists())
        config = self.server.upload_data_dir / 'upload_settings.json'
        self.assertEqual(json.loads(config.read_text(encoding='utf-8')), {'directory': str(folder)})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.request('POST', '/upload/settings', body=b'{}', headers={'Authorization': 'Bearer test-secret'})
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        response.read()
        conn.close()

    def test_destination_reloads_each_request(self):
        import upload_settings
        first = self.configured_destination()
        self.assertEqual(201, self.upload(b'first')[0])
        second = self.root / 'second'
        second.mkdir()
        upload_settings.save_upload_directory(self.server.upload_data_dir, second)
        self.assertEqual(201, self.upload(b'second')[0])
        self.assertEqual((first / 'test.txt').read_bytes(), b'first')
        self.assertEqual((second / 'test.txt').read_bytes(), b'second')

    def test_unavailable_or_corrupt_destination_never_falls_back(self):
        from unittest.mock import patch
        import upload_settings
        folder = self.configured_destination()
        folder.rmdir()
        fallback = self.root / 'fallback'
        with patch.object(upload_settings, 'downloads_folder', return_value=fallback):
            status, result = self.upload()
            self.assertEqual(500, status)
            self.assertNotIn(str(folder), result['error'])
            self.assertFalse(folder.exists())
            (self.server.upload_data_dir / 'upload_settings.json').write_text('{private', encoding='utf-8')
            self.assertEqual(500, self.upload()[0])
        self.assertFalse(fallback.exists())

    def test_explicit_test_override_ignores_corrupt_settings(self):
        self.server.upload_data_dir = self.root / 'data'
        self.server.upload_data_dir.mkdir()
        (self.server.upload_data_dir / 'upload_settings.json').write_text('{broken', encoding='utf-8')
        self.assertEqual(201, self.upload()[0])
        self.assertTrue((self.root / 'test.txt').exists())

    def test_environment_data_directory_used_without_server_attribute(self):
        import upload_settings
        from unittest.mock import patch
        del self.server.downloads_dir
        data = self.root / 'env-data'
        folder = self.root / 'env-target'
        folder.mkdir()
        upload_settings.save_upload_directory(data, folder)
        with patch.dict('os.environ', {'VZAIMOPULT_DATA_DIR': str(data)}):
            self.assertEqual(201, self.upload()[0])
        self.assertEqual((folder / 'test.txt').read_bytes(), b'hello')

    def test_active_upload_keeps_original_directory_snapshot(self):
        import upload_settings
        from unittest.mock import patch
        import file_upload
        first = self.configured_destination()
        second = self.root / 'second'
        second.mkdir()
        original = file_upload.shutil.disk_usage
        def change_setting_after_snapshot(path):
            upload_settings.save_upload_directory(self.server.upload_data_dir, second)
            return original(path)
        with patch.object(file_upload.shutil, 'disk_usage', side_effect=change_setting_after_snapshot):
            self.assertEqual(201, self.upload()[0])
        self.assertEqual((first / 'test.txt').read_bytes(), b'hello')
        self.assertFalse((second / 'test.txt').exists())
        self.assertEqual(upload_settings.upload_directory(self.server.upload_data_dir), second)

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
