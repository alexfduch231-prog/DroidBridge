"""Verify a frozen build matches source and has no runtime files; never runs it."""
import argparse
import json
from pathlib import Path
from build_support import inventory


def audit(output: Path, source: Path):
    manifest = json.loads((output / 'build-manifest.json').read_text(encoding='utf-8'))
    payload = output / 'dist' / 'DroidBridge'
    if inventory(payload) != manifest['payload_sha256']:
        raise ValueError('Payload changed after build')
    artifacts = output / 'artifacts'
    if artifacts.is_dir():
        sums = json.loads((artifacts / 'SHA256SUMS.json').read_text(encoding='utf-8'))
        actual = {name: digest for name, digest in inventory(artifacts).items() if name != 'SHA256SUMS.json'}
        if actual != sums:
            raise ValueError('Installer artifacts changed after build')
    expected = manifest['source_sha256']
    current = {name: inventory_one(source / name) for name in expected}
    if current != expected:
        raise ValueError('Source changed since freeze; rebuild required')
    forbidden = {'token.txt', 'apps.json', 'upload_settings.json', 'client.pid', 'listener.log', 'client.log'}
    forbidden_suffixes = {'.jks', '.keystore', '.pem', '.key', '.log', '.pid'}
    for file in payload.rglob('*'):
        if file.is_file() and (file.name.lower() in forbidden or file.suffix.lower() in forbidden_suffixes):
            raise ValueError('Unexpected private runtime file in payload: ' + file.relative_to(payload).as_posix())
    return {'ok': True, 'integrity_ok': True,
            'publish_allowed': bool(manifest.get('public_release_ready')) and not manifest['contains_ffmpeg'],
            'release_gate': manifest.get('release_gate', 'Release validation required'),
            'source_files': len(expected), 'payload_files': len(manifest['payload_sha256']),
            'contains_ffmpeg': manifest['contains_ffmpeg'], 'self_test': manifest['self_test']}


def inventory_one(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(audit(args.output, args.source), indent=2))
