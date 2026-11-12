"""Sign prepared update metadata with an explicitly supplied private publisher key.

The key is never generated, copied into the repository, or included in release assets.
Run offline after validating the platform binaries and their hashes.
"""
import argparse
import base64
import json
from pathlib import Path

DOMAIN = b'DroidBridge/update-manifest/v1\n'


def sign_payload(payload_bytes, private_key_bytes):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    if len(payload_bytes) > 32768:
        raise ValueError('Metadata is too large')
    key = serialization.load_pem_private_key(private_key_bytes, password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size != 3072:
        raise ValueError('Expected an RSA-3072 publisher key')
    signature = key.sign(DOMAIN + payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    return json.dumps({'payload': base64.b64encode(payload_bytes).decode('ascii'),
                       'signature': base64.b64encode(signature).decode('ascii')},
                      separators=(',', ':')).encode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--private-key', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raw = args.payload.read_bytes()
    if args.output.resolve() in (args.payload.resolve(), args.private_key.resolve()):
        parser.error('Output must not overwrite payload or private key')
    envelope = sign_payload(raw, args.private_key.read_bytes())
    with args.output.open('xb') as stream:
        stream.write(envelope)
    print('Signed update envelope created; private key not exported')


if __name__ == '__main__':
    main()
