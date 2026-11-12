"""Headless pairing-panel lifecycle tests; no GUI or production listener."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'listener'))
from lan_discovery import Adapter
from pairing_panel import PairingController, eligible_adapters, load_pairing_key


class FakeServer:
    instances = []
    def __init__(self, session, data_dir, bind, port):
        self.session, self.bind, self.port = session, bind, port
        self.fingerprint = 'a' * 64
        self.closed = False
        self.instances.append(self)
    def start(self):
        return self
    def close(self):
        self.closed = True


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name)
        self.adapter = Adapter('192.168.1.2', '255.255.255.0', 'AA-BB-CC-DD-EE-FF')
        FakeServer.instances = []
        self.now = 0
        self.control = PairingController(self.path, server_factory=FakeServer, clock=lambda: self.now)
        self.addCleanup(self.control.close)

    def test_key_creation_and_legacy_preservation(self):
        key = load_pairing_key(self.path)
        self.assertGreaterEqual(len(key), 32)
        self.assertEqual(key, load_pairing_key(self.path))
        (self.path / 'token.txt').write_text('A' * 22)
        self.assertEqual('A' * 22, load_pairing_key(self.path))

    def test_invalid_existing_key_is_not_overwritten(self):
        (self.path / 'token.txt').write_text('invalid\nkey')
        with self.assertRaises(ValueError):
            load_pairing_key(self.path)
        self.assertEqual('invalid\nkey', (self.path / 'token.txt').read_text())

    def test_only_rfc1918_adapters(self):
        adapters = [self.adapter, Adapter('8.8.8.8', '255.255.255.0', 'AA-BB-CC-DD-EE-FF'),
                    Adapter('127.0.0.1', '255.0.0.0', 'AA-BB-CC-DD-EE-FF')]
        self.assertEqual([self.adapter], eligible_adapters(adapters))

    def test_rotation_revokes_old_session_and_binds_selected_adapter(self):
        self.control.rotate(self.adapter)
        old = self.control.session
        link = self.control.link
        self.assertEqual(self.adapter.ip, FakeServer.instances[0].bind)
        self.control.rotate(self.adapter)
        self.assertTrue(FakeServer.instances[0].closed)
        self.assertEqual('rejected', old.snapshot()['state'])
        self.assertNotEqual(link, self.control.link)
        self.assertEqual('open', self.control.snapshot()['state'])

    def test_expiry_closes_server_and_clears_link(self):
        self.control.rotate(self.adapter)
        self.now = 120
        self.assertEqual('expired', self.control.snapshot()['state'])
        self.assertTrue(FakeServer.instances[0].closed)
        self.assertEqual('', self.control.link)

    def test_close_revokes_pending_session(self):
        from urllib.parse import parse_qs, urlsplit
        self.control.rotate(self.adapter)
        ticket = parse_qs(urlsplit(self.control.link).query)['ticket'][0]
        self.control.session.claim(ticket, 'Phone')
        self.assertEqual('pending', self.control.snapshot()['state'])
        self.control.close()
        self.assertEqual('rejected', self.control.session.snapshot()['state'])
        self.assertTrue(FakeServer.instances[0].closed)


if __name__ == '__main__':
    unittest.main()
