"""Media-kit contract tests: real files, no execution of untrusted binaries."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import media_bundle as media


def make_kit(root):
    files = {'bin/ffmpeg.exe': b'MZffmpeg', 'bin/ffplay.exe': b'MZffplay',
             'bin/avcodec.dll': b'MZcodec', 'sources/ffmpeg.tar.xz': b'source archive',
             'sources/build.sh': b'./configure --disable-gpl --disable-nonfree\n',
             'licenses/FFmpeg.txt': b'LGPL license text'}
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = {'schema_version': 1,
                **{key: {name: hashlib.sha256(data).hexdigest() for name, data in files.items() if name.startswith(prefix)}
                   for key, prefix in [('runtime_sha256', 'bin/'), ('source_sha256', 'sources/'), ('license_sha256', 'licenses/')]},
                'components': [{'name': 'FFmpeg', 'version': '9.0.2', 'license': 'LGPL-2.1-or-later',
                                'source_url': 'https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz',
                                'source_paths': ['sources/ffmpeg.tar.xz'], 'license_paths': ['licenses/FFmpeg.txt']}]}
    save_manifest(root, manifest)
    return manifest


def save_manifest(root, manifest):
    (root / 'media-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


class MediaBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'kit'
        self.manifest = make_kit(self.root)

    def test_validated_stage_flattens_bin_and_preserves_all_source_proof(self):
        target = Path(self.temp.name) / 'media'
        self.assertEqual(media.validate_media_bundle(self.root), self.manifest)
        media.stage_media_bundle(self.root, target)
        self.assertEqual((target / 'ffmpeg.exe').read_bytes(), b'MZffmpeg')
        self.assertEqual((target / 'avcodec.dll').read_bytes(), b'MZcodec')
        self.assertTrue((target / 'sources/ffmpeg.tar.xz').is_file())
        self.assertEqual(media.validate_media_bundle(target, staged=True), self.manifest)

    def test_rejects_extra_file_anywhere_including_runtime_PE(self):
        for name in ['bin/surprise.dll', 'secret.txt', 'sources/extra.exe']:
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'MZprivate')
                with self.assertRaises(ValueError):
                    media.validate_media_bundle(self.root)
                path.unlink()

    def test_every_hash_is_checked(self):
        for key in ['runtime_sha256', 'source_sha256', 'license_sha256']:
            path = self.root / next(iter(self.manifest[key]))
            original = path.read_bytes()
            path.write_bytes(b'tampered')
            with self.subTest(key=key), self.assertRaises(ValueError):
                media.validate_media_bundle(self.root)
            path.write_bytes(original)

    def test_rejects_missing_runtime_and_missing_source_recipe(self):
        for name in ['bin/ffmpeg.exe', 'bin/ffplay.exe', 'sources/build.sh']:
            original = (self.root / name).read_bytes()
            (self.root / name).unlink()
            with self.subTest(name=name), self.assertRaises(ValueError):
                media.validate_media_bundle(self.root)
            (self.root / name).write_bytes(original)

    def test_rejects_path_escapes_windows_aliases_and_bad_hashes(self):
        for path in ['../escape.exe', 'bin/../escape.exe', 'bin/C:bad.exe', 'bin\\bad.exe',
                     '/bin/bad.exe', 'bin/CON.dll', 'bin/bad.exe.', 'bin/FFMPEG.EXE']:
            manifest = json.loads(json.dumps(self.manifest))
            manifest['runtime_sha256'][path] = '0' * 64
            save_manifest(self.root, manifest)
            with self.subTest(path=path), self.assertRaises(ValueError):
                media.validate_media_bundle(self.root)
        save_manifest(self.root, self.manifest)
        self.manifest['source_sha256']['sources/build.sh'] = 'not a sha256'
        save_manifest(self.root, self.manifest)
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)

    def test_rejects_symlinks_even_with_matching_hash(self):
        path = self.root / 'bin/avcodec.dll'
        path.unlink()
        outside = Path(self.temp.name) / 'outside.dll'
        outside.write_bytes(b'MZcodec')
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest('Host does not permit symlinks')
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)

    def test_rejects_nonfree_and_missing_component_proof(self):
        for change in [lambda m: m['components'][0].update(license='nonfree'),
                       lambda m: m['components'][0].update(source_paths=[]),
                       lambda m: m['components'][0].update(license_paths=['licenses/missing']),
                       lambda m: m.update(schema_version=2),
                       lambda m: m.update(nonfree=True)]:
            manifest = json.loads(json.dumps(self.manifest))
            change(manifest)
            save_manifest(self.root, manifest)
            with self.assertRaises(ValueError):
                media.validate_media_bundle(self.root)

    def test_rejects_enabled_nonfree_even_with_correct_recipe_hash(self):
        path = self.root / 'sources/build.sh'
        path.write_bytes(b'./configure --enable-nonfree')
        self.manifest['source_sha256']['sources/build.sh'] = hashlib.sha256(path.read_bytes()).hexdigest()
        save_manifest(self.root, self.manifest)
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)

    def test_rejects_duplicate_manifest_keys(self):
        path = self.root / 'media-manifest.json'
        text = path.read_text(encoding='utf-8')
        path.write_text(text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)

    def test_rejects_nonfile_and_listed_PE_source(self):
        path = self.root / 'bin/avcodec.dll'
        path.unlink()
        path.mkdir()
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)
        path.rmdir()
        path.write_bytes(b'MZcodec')
        source = self.root / 'sources/ffmpeg.tar.xz'
        source.write_bytes(b'MZopaque executable')
        self.manifest['source_sha256']['sources/ffmpeg.tar.xz'] = hashlib.sha256(source.read_bytes()).hexdigest()
        save_manifest(self.root, self.manifest)
        with self.assertRaises(ValueError):
            media.validate_media_bundle(self.root)

    def test_rejects_missing_component_archives_or_recipe_even_when_allowlisted(self):
        for name in ['sources/build.sh', 'sources/ffmpeg.tar.xz']:
            manifest = json.loads(json.dumps(self.manifest))
            del manifest['source_sha256'][name]
            data = (self.root / name).read_bytes()
            (self.root / name).unlink()
            save_manifest(self.root, manifest)
            with self.subTest(name=name), self.assertRaises(ValueError):
                media.validate_media_bundle(self.root)
            (self.root / name).write_bytes(data)

    def test_refuses_existing_stage(self):
        with self.assertRaises(FileExistsError):
            media.stage_media_bundle(self.root, self.root)


if __name__ == '__main__':
    unittest.main()
