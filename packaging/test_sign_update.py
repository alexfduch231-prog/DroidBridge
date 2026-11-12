import base64
import importlib.util
import json
from pathlib import Path
import unittest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

spec = importlib.util.spec_from_file_location('sign_update', Path(__file__).with_name('sign_update.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SignUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.pem = cls.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    def test_domain_separated_exact_raw_bytes(self):
        raw = b'{"synthetic":true}'
        envelope = json.loads(module.sign_payload(raw, self.pem))
        self.assertEqual(set(envelope), {'payload', 'signature'})
        self.assertEqual(base64.b64decode(envelope['payload']), raw)
        self.key.public_key().verify(base64.b64decode(envelope['signature']), b'DroidBridge/update-manifest/v1\n' + raw, padding.PKCS1v15(), hashes.SHA256())

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            module.sign_payload(b'x' * 32769, self.pem)

    def test_wrong_key_size_rejected(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        with self.assertRaises(ValueError):
            module.sign_payload(b'{}', pem)

if __name__ == '__main__':
    unittest.main()
