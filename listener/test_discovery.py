"""Discovery contract tests: no real pairing keys, no deployed listener required."""
import hashlib
import hmac
import importlib.util
import pathlib
import socket
import threading
import time
import unittest

MODULE = pathlib.Path(__file__).with_name('lan_discovery.py')
spec = importlib.util.spec_from_file_location('lan_discovery', MODULE)
d = importlib.util.module_from_spec(spec) if MODULE.exists() else None
if d is not None:
    spec.loader.exec_module(d)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(d, 'lan_discovery implementation is missing')
        self.key = 'test-only-pairing-secret'
        self.nonce = '0123456789abcdef' * 2

    def test_request_hmac_and_no_key_on_wire(self):
        packet = d.make_request(self.key, self.nonce)
        self.assertNotIn(self.key.encode(), packet)
        self.assertEqual(self.nonce, d.verify_request(packet, self.key))
        self.assertIsNone(d.verify_request(packet, 'wrong-key'))
        self.assertIsNone(d.verify_request(packet.replace(b'request', b'response'), self.key))
        self.assertIsNone(d.verify_request(packet, ''))

    def test_malformed_nonce_and_oversized_packets(self):
        for nonce in ('', 'x' * 32, 'a' * 31, 'a' * 64):
            body = ('PCMOTE_DISCOVERY|1|request|' + nonce).encode()
            packet = body + b'|' + hmac.new(self.key.encode(), body, hashlib.sha256).hexdigest().encode()
            self.assertIsNone(d.verify_request(packet, self.key))
        for packet in (b'\xff', b'a' * 2049, b'', b'PCMOTE_DISCOVERY|1|request'):
            self.assertIsNone(d.verify_request(packet, self.key))

    def test_response_nonce_signature_and_fields(self):
        adapter = d.Adapter('10.4.16.7', '255.255.240.0', '02-11-22-33-44-55')
        packet = d.make_response(self.key, self.nonce, 8765, adapter)
        result = d.verify_response(packet, self.key, self.nonce)
        self.assertEqual((8765, adapter.mac, '10.4.31.255'), result)
        self.assertIsNone(d.verify_response(packet, self.key, 'f' * 32))
        self.assertIsNone(d.verify_response(packet.replace(b'8765', b'9999'), self.key, self.nonce))
        self.assertIsNone(d.verify_response(packet, 'wrong', self.nonce))

    def test_select_exact_routed_adapter_not_first_mac(self):
        first = d.Adapter('10.0.0.2', '255.255.255.0', '02-AA-AA-AA-AA-AA')
        second = d.Adapter('172.16.8.3', '255.255.252.0', '02-BB-BB-BB-BB-BB')
        self.assertIs(second, d.select_adapter([first, second], '172.16.8.3', '172.16.11.9'))
        self.assertIsNone(d.select_adapter([first, second], '172.16.8.3', '8.8.8.8'))
        self.assertIsNone(d.select_adapter([first, second], '192.0.2.1', '192.0.2.2'))

    def test_rate_limit_bounded_and_recovers(self):
        limiter = d.RateLimiter(interval=1.0, maximum=4)
        self.assertTrue(limiter.allow('a', 10.0))
        self.assertFalse(limiter.allow('a', 10.1))
        self.assertTrue(limiter.allow('a', 11.1))
        for index in range(20):
            limiter.allow(str(index), 12.0)
        self.assertLessEqual(len(limiter.seen), 4)

    def test_live_loopback_valid_invalid_and_stop_timeout(self):
        adapter = d.Adapter('127.0.0.1', '255.0.0.0', '02-11-22-33-44-55')
        server = d.DiscoveryServer(self.key, 8765, host='127.0.0.1', port=0,
                                   adapters=lambda: [adapter], route=lambda peer: '127.0.0.1')
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(0.4)
                client.sendto(d.make_request('wrong-key', self.nonce), server.address)
                with self.assertRaises(socket.timeout):
                    client.recvfrom(2048)
                client.sendto(d.make_request(self.key, self.nonce), server.address)
                packet, source = client.recvfrom(2048)
                self.assertEqual('127.0.0.1', source[0])
                self.assertEqual((8765, adapter.mac, '127.255.255.255'),
                                 d.verify_response(packet, self.key, self.nonce))
                client.sendto(d.make_request(self.key, self.nonce), server.address)
                with self.assertRaises(socket.timeout):
                    client.recvfrom(2048)
        finally:
            server.close()
            worker.join(1)
        self.assertFalse(worker.is_alive(), 'bounded receive timeout must permit shutdown')

    def test_activity_lifecycle_and_listener_integration(self):
        root = MODULE.parent.parent
        activity = (root / 'app/src/ru/alexv/pcmote/MainActivity.java').read_text(encoding='utf-8')
        listener = MODULE.with_name('pc-listener.py').read_text(encoding='utf-8')
        manifest = (root / 'app/AndroidManifest.xml').read_text(encoding='utf-8')
        self.assertIn('WifiManager.NETWORK_STATE_CHANGED_ACTION', activity)
        self.assertIn('unregisterReceiver(discoveryReceiver)', activity)
        self.assertIn('discoveryEditRevision != editRevision', activity)
        self.assertIn('DiscoveryServer(token, args.port', listener)
        self.assertIn('discovery.close()', listener)
        import xml.etree.ElementTree as ET
        release = ET.fromstring(manifest)
        self.assertGreaterEqual(int(release.get('{http://schemas.android.com/apk/res/android}versionCode')), 22)
        for name in ('DEF_MAC', 'DEF_BCAST', 'DEF_HOST'):
            self.assertIn('String ' + name + ' = "";', activity)
        self.assertFalse('host.substring(0, dot) + ".255"' in activity,
                         'Do not guess a /24 broadcast without an interface mask')

    def test_java_protocol_cross_language(self):
        import subprocess
        import tempfile
        import shutil
        source = MODULE.parent.parent / 'app/src/ru/alexv/pcmote/PcDiscovery.java'
        self.assertTrue(source.exists(), 'Android discovery helper is missing')
        import os
        executable = '.exe' if os.name == 'nt' else ''
        home = pathlib.Path(os.environ.get('JAVA_HOME', '')) / 'bin'
        home_javac = home / ('javac' + executable)
        javac = str(home_javac) if home_javac.is_file() else (shutil.which('javac') or '')
        java = str(pathlib.Path(javac).with_name('java' + executable)) if javac else ''
        if not pathlib.Path(javac).is_file() or not pathlib.Path(java).is_file():
            self.skipTest('JDK required: put javac/java on PATH or configure JAVA_HOME')
        response = d.make_response(self.key, self.nonce, 8765,
                                   d.Adapter('10.4.16.7', '255.255.240.0', '02-11-22-33-44-55')).decode()
        harness = '''package ru.alexv.pcmote;
public class DiscoveryContract {
 public static void main(String[] args) throws Exception {
  String key = args[0], nonce = args[1], response = args[2];
  PcDiscovery.Result r = PcDiscovery.verify(response.getBytes("US-ASCII"), key, nonce, "10.4.16.7");
  if (r == null || r.port != 8765 || !r.broadcast.equals("10.4.31.255")) throw new AssertionError("valid response");
  if (PcDiscovery.verify(response.getBytes("US-ASCII"), "wrong", nonce, "10.4.16.7") != null) throw new AssertionError("wrong key");
  if (PcDiscovery.verify(response.getBytes("US-ASCII"), key, "ffffffffffffffffffffffffffffffff", "10.4.16.7") != null) throw new AssertionError("nonce replay");
  if (PcDiscovery.verify(response.replace("8765", "9999").getBytes("US-ASCII"), key, nonce, "10.4.16.7") != null) throw new AssertionError("tamper");
  PcDiscovery.Result other = new PcDiscovery.Result("10.4.16.8", 8765, "02-AA-AA-AA-AA-AA", "10.4.31.255");
  if (PcDiscovery.prefer(other, r, "02-11-22-33-44-55", "") != r) throw new AssertionError("paired MAC preference");
  if (PcDiscovery.prefer(r, other, "02-11-22-33-44-55", "10.4.16.8") != r) throw new AssertionError("MAC before stale IP");
  System.out.print(new String(PcDiscovery.request(key, nonce), "US-ASCII"));
 }
}'''
        with tempfile.TemporaryDirectory(prefix='pcmote-discovery-test-') as temp:
            path = pathlib.Path(temp) / 'DiscoveryContract.java'
            path.write_text(harness, encoding='utf-8')
            compiled = subprocess.run([javac, '-encoding', 'UTF-8', '-d', temp, str(source), str(path)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, compiled.stderr)
            run = subprocess.run([java, '-cp', temp, 'ru.alexv.pcmote.DiscoveryContract', self.key, self.nonce, response], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual(self.nonce, d.verify_request(run.stdout.encode(), self.key))

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows IP Helper API')
    def test_windows_adapter_inventory(self):
        adapters = d.windows_adapters()
        self.assertTrue(adapters)
        for adapter in adapters:
            self.assertEqual(6, len(bytes.fromhex(adapter.mac.replace('-', ''))))
            socket.inet_aton(adapter.ip)
            socket.inet_aton(adapter.broadcast)


if __name__ == '__main__':
    unittest.main(verbosity=2)
