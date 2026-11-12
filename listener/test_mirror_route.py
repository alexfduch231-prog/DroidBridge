"""Authenticated mirror requests derive their target from the TCP peer only."""
import http.client
import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('mirror_listener', Path(__file__).with_name('pc-listener.py'))
listener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(listener)


class MirrorRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = listener.Server(('127.0.0.1', 0), listener.Handler)
        self.server.token = 'test-secret'
        self.server.dry_run = False
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self, query):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request('GET', '/mirror?' + query)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_authenticated_request_ignores_query_target_and_uses_tcp_peer(self):
        with patch.object(listener, 'client_alive', return_value=False), patch.object(
                listener, 'start_mirror_client', return_value=(True, '')) as start:
            status, _ = self.request('key=test-secret&port=8769&ip=192.0.2.10&host=192.0.2.20')
        self.assertEqual(status, 200)
        start.assert_called_once_with('127.0.0.1', 8769)

    def test_wrong_token_never_opens_viewer(self):
        with patch.object(listener, 'start_mirror_client') as start:
            status, _ = self.request('key=wrong&port=8768')
        self.assertEqual(status, 403)
        start.assert_not_called()

    def test_privileged_and_out_of_range_ports_never_open_viewer(self):
        with patch.object(listener, 'start_mirror_client') as start:
            for port in (0, 80, 65536):
                with self.subTest(port=port):
                    self.assertEqual(self.request('key=test-secret&port=' + str(port))[0], 400)
        start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
