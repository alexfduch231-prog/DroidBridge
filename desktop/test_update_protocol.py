"""Offline protocol tests; the fixture is synthetic, not a downloadable release."""
import base64
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import tempfile
import unittest

# Public synthetic signature fixture only; no private signing material.
FIXTURE = b'{"payload":"eyJhbmRyb2lkIjp7ImFzc2V0TmFtZSI6IkRyb2lkQnJpZGdlLTEuMTUtYW5kcm9pZC5hcGsiLCJtaW5TZGsiOjIxLCJwYWNrYWdlTmFtZSI6InJ1LmFsZXh2LnBjbW90ZSIsInNoYTI1NiI6ImJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmIiLCJzaWduZXJDZXJ0U2hhMjU2IjpbIjZlMWY5YzdiMGVjZTM3MjNkOTI5YTVmNGQzYmZlYjUwMjM5M2M4NTE5OWRlYTZlN2M4MmQxOGE3ZGQ1Mzc3YTAiXSwic2l6ZSI6MTIzLCJ1cmwiOiJodHRwczovL2dpdGh1Yi5jb20vYWxleGZkdWNoMjMxLXByb2cvRHJvaWRCcmlkZ2UvcmVsZWFzZXMvZG93bmxvYWQvdjEuMC40L0Ryb2lkQnJpZGdlLTEuMTUtYW5kcm9pZC5hcGsiLCJ2ZXJzaW9uQ29kZSI6MjUsInZlcnNpb25OYW1lIjoiMS4xNSJ9LCJjaGFubmVsIjoic3RhYmxlIiwiZXhwaXJlc0F0IjoiMjAzMC0wMS0wMVQwMDowMDowMFoiLCJwdWJsaXNoZWRBdCI6IjIwMjYtMTEtMTJUMTA6MDA6MDBaIiwicmVwb3NpdG9yeSI6ImFsZXhmZHVjaDIzMS1wcm9nL0Ryb2lkQnJpZGdlIiwic2NoZW1hIjoxLCJzZXF1ZW5jZSI6MSwid2luZG93cyI6eyJhcmNoaXRlY3R1cmUiOiJ4NjQiLCJhc3NldE5hbWUiOiJEcm9pZEJyaWRnZS0xLjAuNC13aW5kb3dzLXg2NC1zZXR1cC5leGUiLCJzaGEyNTYiOiJhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhIiwic2l6ZSI6MTIzLCJ1cmwiOiJodHRwczovL2dpdGh1Yi5jb20vYWxleGZkdWNoMjMxLXByb2cvRHJvaWRCcmlkZ2UvcmVsZWFzZXMvZG93bmxvYWQvdjEuMC40L0Ryb2lkQnJpZGdlLTEuMC40LXdpbmRvd3MteDY0LXNldHVwLmV4ZSIsInZlcnNpb24iOiIxLjAuNCJ9fQ==","signature":"m2XBPEcm4ii3MUnw0N7zefjPRaWNgLJP6ijV9Hc5GqoKaLcbfb3z5/SmPD5bReIvxoXGPnzQ41aVGDTQzngyxKERi10DJeGNAVFZX07x4glrAwnWDDHtX2VpqYHIIa7rPcff3n+NUjsunlM/nuOhKoKNXyyJMQhPBtaJHUBaPIZ/KM0ZiYVpfAPgPSdvGodtkzOqXHE93smvGJV6wvJ02EINiJUf/SJBESPluMRG/+Nokz7mWf/64BfK6wY+Pc8udUUfW8u/5hTFRLOf7610zKpHkE8L4Ftuk2tI5ZAeeXAcb14zFpXABEMKnfEJMEZ9oljVXZzhye9yn+qrq9clJwxq0voONhIoJrAat4U1RULHG3vctNziKP/68G6tBlxFTTyzAhBeSROAKaIyW0XmI3b5ACuinn99zCpxM8sUjWTMNgwTp3KaUPlBRZUnBl7aVQUrPBxR+Ndz6/9CxX/ujXQ3xCVCRRkSHzXlpsMiGa9hluFuD6nQZHUzJ1qe27Yb"}'
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.p = importlib.import_module('update_protocol')
        self.envelope = FIXTURE
        self.payload = json.loads(base64.b64decode(json.loads(self.envelope)['payload']))

    def test_signed_fixture_verified_at_explicit_clock(self):
        self.assertEqual(self.p.verify_manifest(self.envelope, now=NOW)['sequence'], 1)

    def test_tampered_payload_rejected_before_json(self):
        env = json.loads(self.envelope)
        env['payload'] = base64.b64encode(b'not json').decode()
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.p.verify_manifest(json.dumps(env).encode(), now=NOW)

    def test_envelope_duplicates_and_limits(self):
        for data in (b'{"payload":"a","payload":"b","signature":"c"}', b' ' * 65537):
            with self.assertRaises(ValueError):
                self.p.verify_manifest(data, now=NOW)

    def test_expiration_uses_explicit_clock(self):
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.p.verify_manifest(self.envelope, now=datetime(2031, 1, 1, tzinfo=timezone.utc))

    def test_both_platforms_required_and_integer_not_bool(self):
        for mutate in (lambda x: x.pop('android'), lambda x: x.update(sequence=True),
                       lambda x: x['windows'].update(version='1.2'),
                       lambda x: x['android'].update(size=128 * 1024 * 1024 + 1),
                       lambda x: x['windows'].update(url='https://github.com/evil/repo/releases/download/x/a.exe')):
            payload = json.loads(json.dumps(self.payload))
            mutate(payload)
            with self.assertRaises(ValueError):
                self.p.validate_payload(payload, now=NOW)

    def test_redirect_policy_exact_hosts_no_credentials_ports_or_http(self):
        for url in ('http://github.com/a', 'https://github.com.evil/a', 'https://u@github.com/a',
                    'https://github.com:443/a', 'https://objects.githubusercontent.com.evil/a'):
            with self.assertRaises(ValueError):
                self.p.validate_https_url(url)
        for host in self.p.ALLOWED_HOSTS:
            self.p.validate_https_url('https://' + host + '/a')

    def test_strict_duplicate_keys_payload(self):
        with self.assertRaises(ValueError):
            self.p.strict_json(b'{"sequence":1,"sequence":2}')

    def test_bounded_atomic_sequence_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.p.SequenceState(Path(directory))
            state.accept(3)
            self.assertEqual(self.p.SequenceState(Path(directory)).maximum(), 3)
            state.accept(3)
            with self.assertRaises(ValueError):
                state.accept(2)
            self.assertFalse(list(Path(directory).glob('*.tmp')))
            (Path(directory) / 'update_state.json').write_text('{broken')
            with self.assertRaises(ValueError):
                state.maximum()

    def test_shared_signed_negative_vectors(self):
        vectors = json.loads((Path(__file__).resolve().parents[1] / 'app' / 'test-update-vectors.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(vectors), 24)
        for vector in vectors:
            with self.subTest(vector=vector['name']):
                with self.assertRaises(ValueError):
                    self.p.verify_manifest(json.dumps(vector['envelope']).encode(), now=NOW)

    def test_version_order_has_no_equal_version_loop(self):
        self.assertFalse(self.p.is_newer('1.0.4', '1.0.4'))
        self.assertFalse(self.p.is_newer('1.0.3', '1.0.4'))
        self.assertTrue(self.p.is_newer('1.0.10', '1.0.4'))


if __name__ == '__main__':
    unittest.main()
