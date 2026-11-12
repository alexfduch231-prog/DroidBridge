import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PackagingTests(unittest.TestCase):
    def test_staging_is_exact_allowlist_not_recursive_copy(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'src', Path(tmp) / 'dst'
            for relative in p.SOURCE_FILES:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('# public source', encoding='utf-8')
            for relative in ['listener/token.txt', 'listener/apps.json', 'listener/listener.log', 'client/client.pid', 'keystore.jks', 'desktop/private.py']:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('PRIVATE SENTINEL', encoding='utf-8')
            p.stage_sources(source, target)
            actual = {f.relative_to(target).as_posix() for f in target.rglob('*') if f.is_file()}
            self.assertEqual(actual, set(p.SOURCE_FILES))
            self.assertNotIn('PRIVATE SENTINEL', ''.join(f.read_text() for f in target.rglob('*') if f.is_file()))

    def test_upload_modules_are_staged_without_user_settings(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        modules = ('listener/upload_settings.py', 'desktop/upload_panel.py')
        configs = ('upload_settings.json', 'listener/upload_settings.json',
                   'desktop/upload_settings.json', 'listener/UPLOAD_SETTINGS.JSON')
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'src', Path(tmp) / 'dst'
            for relative in set(p.SOURCE_FILES) | set(modules):
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('# public upload module', encoding='utf-8')
            for relative in configs:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('PRIVATE UPLOAD SETTINGS', encoding='utf-8')
            p.stage_sources(source, target)
            for relative in modules:
                with self.subTest(module=relative):
                    self.assertTrue((target / relative).is_file())
                    self.assertEqual((target / relative).read_text(), '# public upload module')
            for relative in configs:
                with self.subTest(config=relative):
                    self.assertFalse((target / relative).exists())
            self.assertFalse(any(f.name.lower() == 'upload_settings.json'
                                 for f in target.rglob('*')))

    def test_audit_rejects_upload_settings_even_with_valid_payload_hash(self):
        import hashlib
        import json
        import sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        for relative in ('upload_settings.json', '_internal/listener/upload_settings.json',
                         '_internal/desktop/UPLOAD_SETTINGS.JSON'):
            with self.subTest(config=relative), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'build'
                payload = output / 'dist' / 'DroidBridge'
                file = payload / relative
                file.parent.mkdir(parents=True)
                data = b'{"upload_directory": "private"}'
                file.write_bytes(data)
                manifest = {'source_sha256': {},
                            'payload_sha256': {relative: hashlib.sha256(data).hexdigest()},
                            'contains_ffmpeg': False, 'self_test': {'ok': True}}
                (output / 'build-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Unexpected private runtime file in payload:'):
                    p.audit(output, Path(tmp) / 'source')

    def test_update_modules_are_allowlisted_without_private_update_state(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        modules = {'desktop/update_protocol.py', 'desktop/update_manager.py', 'desktop/update_helper.py'}
        self.assertTrue(modules <= set(p.SOURCE_FILES))
        self.assertEqual(len(p.SOURCE_FILES), 21)
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'source', Path(tmp) / 'staged'
            for relative in p.SOURCE_FILES:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('# source with public verification key only')
            for relative in ['update_state.json', 'desktop/UPDATE_STATE.JSON', 'listener/update_state.json',
                             'desktop/publishing-private-key.pem']:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('PRIVATE SENTINEL')
            p.stage_sources(source, target)
            actual = {f.relative_to(target).as_posix() for f in target.rglob('*') if f.is_file()}
            self.assertEqual(actual, set(p.SOURCE_FILES))
            self.assertFalse(any('PRIVATE SENTINEL' in f.read_text() for f in target.rglob('*') if f.is_file()))

    def test_audit_rejects_private_update_state_nested_case_insensitive(self):
        import json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        from build_support import inventory
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        for relative in ['update_state.json', '_internal/desktop/UPDATE_STATE.JSON', 'media/sources/update_State.json']:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'build'
                payload = output / 'dist' / 'DroidBridge'
                file = payload / relative
                file.parent.mkdir(parents=True)
                file.write_text('{"pending":"private"}')
                manifest = {'source_sha256': {}, 'payload_sha256': inventory(payload),
                            'contains_ffmpeg': False, 'self_test': {'ok': True}}
                (output / 'build-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'Unexpected private runtime file in payload:'):
                    p.audit(output, Path(tmp) / 'source')

    def test_resumable_upload_module_is_allowlisted(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        self.assertIn('listener/resumable_upload.py', p.SOURCE_FILES)

    def test_audit_rejects_resume_state_directories_and_temporary_files(self):
        import json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        from build_support import inventory
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        cases = [('resumable-uploads', True), ('_internal/RESUMABLE-UPLOADS/state.json', False),
                 ('_internal/.PCMOTE-RESUME-deadbeef', True), ('.pcmote-resume-part.bin', False)]
        for relative, directory in cases:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'build'
                payload = output / 'dist' / 'DroidBridge'
                path = payload / relative
                if directory:
                    path.mkdir(parents=True)
                else:
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b'PRIVATE RESUME STATE')
                manifest = {'source_sha256': {}, 'payload_sha256': inventory(payload),
                            'contains_ffmpeg': False, 'self_test': {'ok': True}}
                (output / 'build-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'Unexpected private runtime'):
                    p.audit(output, Path(tmp) / 'source')

    def test_android_setup_module_is_allowlisted(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        self.assertIn('desktop/android_setup.py', p.SOURCE_FILES)

    def test_audit_rejects_android_setup_preferences(self):
        import hashlib, json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            payload = output / 'dist' / 'DroidBridge'
            file = payload / '_internal' / 'ANDROID_SETUP.JSON'
            file.parent.mkdir(parents=True)
            data = b'{"show_on_startup":false}'
            file.write_bytes(data)
            manifest = {'source_sha256': {}, 'payload_sha256': {'_internal/ANDROID_SETUP.JSON': hashlib.sha256(data).hexdigest()}, 'contains_ffmpeg': False, 'self_test': {'ok': True}}
            (output / 'build-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unexpected private runtime file in payload:'):
                p.audit(output, Path(tmp) / 'source')

    def test_media_modules_are_staged_without_local_settings(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        self.assertIn('listener/media_tools.py', p.SOURCE_FILES)
        self.assertIn('desktop/media_setup.py', p.SOURCE_FILES)

    def test_audit_rejects_media_settings_even_with_valid_payload_hash(self):
        import hashlib, json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            payload = output / 'dist' / 'DroidBridge'
            file = payload / '_internal' / 'MEDIA_SETTINGS.JSON'
            file.parent.mkdir(parents=True)
            data = b'{"directory":"private"}'
            file.write_bytes(data)
            manifest = {'source_sha256': {}, 'payload_sha256': {'_internal/MEDIA_SETTINGS.JSON': hashlib.sha256(data).hexdigest()}, 'contains_ffmpeg': False, 'self_test': {'ok': True}}
            (output / 'build-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unexpected private runtime file in payload:'):
                p.audit(output, Path(tmp) / 'source')

    def test_existing_stage_is_rejected_to_avoid_stale_secrets(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                p.stage_sources(Path(tmp), Path(tmp))

    def test_allowlisted_link_cannot_escape_source(self):
        p = load('build_support', ROOT / 'packaging' / 'build_support.py')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'src'
            for relative in p.SOURCE_FILES:
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('# source')
            first = source / p.SOURCE_FILES[0]
            first.unlink()
            secret = Path(tmp) / 'secret.py'
            secret.write_text('PRIVATE SENTINEL')
            try:
                first.symlink_to(secret)
            except OSError:
                self.skipTest('Host does not permit file symlinks')
            with self.assertRaises(ValueError):
                p.stage_sources(source, Path(tmp) / 'stage')

    def test_invalid_component_cannot_be_spawned(self):
        p = load('desktop_runtime', ROOT / 'desktop' / 'runtime.py')
        with self.assertRaises(ValueError):
            p.child_command('calc.exe')

    def test_invalid_component_cannot_be_loaded(self):
        p = load('desktop_runtime', ROOT / 'desktop' / 'runtime.py')
        with self.assertRaises(ValueError):
            p.load_component('calc.exe')

    def test_phone_address_is_ip_only_and_no_command_injection(self):
        p = load('desktop_runtime', ROOT / 'desktop' / 'runtime.py')
        self.assertEqual(p.phone_address(' 192.168.1.2 '), '192.168.1.2')
        self.assertEqual(p.phone_address('::1'), '::1')
        for value in ['localhost', '--help', '1.2.3.4 & calc', '', '999.1.1.1']:
            with self.assertRaises(ValueError):
                p.phone_address(value)

    def test_audit_checks_installer_hashes(self):
        import json
        import sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            source = Path(tmp) / 'source'
            (output / 'dist' / 'DroidBridge').mkdir(parents=True)
            (output / 'artifacts').mkdir()
            (output / 'build-manifest.json').write_text(json.dumps({'source_sha256': {}, 'payload_sha256': {}, 'contains_ffmpeg': False, 'self_test': {'ok': True}}))
            (output / 'artifacts' / 'setup.exe').write_bytes(b'altered installer')
            (output / 'artifacts' / 'SHA256SUMS.json').write_text(json.dumps({'setup.exe': 'incorrect'}))
            with self.assertRaises(ValueError):
                p.audit(output, source)

    def test_integrity_success_does_not_authorize_publication(self):
        import json
        import sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            source = Path(tmp) / 'source'
            (output / 'dist' / 'DroidBridge').mkdir(parents=True)
            for full, validated, expected in [(False, False, False), (False, True, True)]:
                (output / 'build-manifest.json').write_text(json.dumps({'source_sha256': {}, 'payload_sha256': {}, 'contains_ffmpeg': full, 'self_test': {'ok': True}, 'public_release_ready': validated}))
                result = p.audit(output, source)
                self.assertTrue(result['integrity_ok'])
                self.assertEqual(result['publish_allowed'], expected)

    def test_build_accepts_reviewed_media_before_source_staging_without_freezer(self):
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT / 'packaging'))
        from test_media_bundle import make_kit
        p = load('windows_build_test', ROOT / 'packaging' / 'build_windows.py')
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'kit'
            make_kit(kit)
            arguments = ['build_windows.py', '--output', str(Path(tmp) / 'build'), '--media-root', str(kit)]
            with patch.object(sys, 'argv', arguments), patch.object(sys, 'prefix', 'isolated-test-venv'):
                with patch.object(p, 'stage_sources', side_effect=RuntimeError('STOP before freezer')):
                    with self.assertRaisesRegex(RuntimeError, 'STOP before freezer'):
                        p.main()
            (kit / 'secret.txt').write_text('private')
            with patch.object(sys, 'argv', arguments), patch.object(sys, 'prefix', 'isolated-test-venv'):
                with patch.object(p, 'stage_sources') as stage:
                    with self.assertRaises((ValueError, SystemExit)):
                        p.main()
                    stage.assert_not_called()

    def test_audit_requires_media_source_proof_regardless_of_release_flag(self):
        import json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        for ready in [False, True]:
            with self.subTest(ready=ready), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'build'
                (output / 'dist' / 'DroidBridge').mkdir(parents=True)
                manifest = {'source_sha256': {}, 'payload_sha256': {}, 'contains_ffmpeg': True,
                            'self_test': {'ok': True}, 'public_release_ready': ready}
                (output / 'build-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'media|Media'):
                    p.audit(output, Path(tmp) / 'source')

    def test_audit_accepts_complete_staged_media_but_keeps_release_gate(self):
        import json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        from test_media_bundle import make_kit
        from media_bundle import stage_media_bundle
        from build_support import inventory
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            payload = output / 'dist' / 'DroidBridge'
            kit = Path(tmp) / 'kit'
            proof = make_kit(kit)
            stage_media_bundle(kit, payload / 'media')
            manifest = {'source_sha256': {}, 'payload_sha256': inventory(payload),
                        'contains_ffmpeg': True, 'self_test': {'ok': True},
                        'media_bundle': proof, 'public_release_ready': False}
            path = output / 'build-manifest.json'
            path.write_text(json.dumps(manifest))
            result = p.audit(output, Path(tmp) / 'source')
            self.assertTrue(result['media_source_verified'])
            self.assertFalse(result['publish_allowed'])
            manifest['public_release_ready'] = True
            path.write_text(json.dumps(manifest))
            self.assertTrue(p.audit(output, Path(tmp) / 'source')['publish_allowed'])
            manifest['media_bundle']['components'][0]['version'] = 'wrong'
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                p.audit(output, Path(tmp) / 'source')

    def test_audit_cannot_hide_media_with_false_contains_flag(self):
        import json, sys
        sys.path.insert(0, str(ROOT / 'packaging'))
        from build_support import inventory
        p = load('artifact_audit', ROOT / 'packaging' / 'audit_artifact.py')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'build'
            payload = output / 'dist' / 'DroidBridge'
            media = payload / 'media'
            media.mkdir(parents=True)
            (media / 'ffmpeg.exe').write_bytes(b'MZ')
            manifest = {'source_sha256': {}, 'payload_sha256': inventory(payload), 'contains_ffmpeg': False,
                        'self_test': {'ok': True}, 'public_release_ready': True}
            (output / 'build-manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'media|Media|FFmpeg'):
                p.audit(output, Path(tmp) / 'source')

    def test_data_path_is_not_install_directory(self):
        p = load('desktop_runtime', ROOT / 'desktop' / 'runtime.py')
        self.assertEqual(p.data_directory({'LOCALAPPDATA': 'D:/test-user'}), Path('D:/test-user') / 'VzaimoPult')

if __name__ == '__main__':
    unittest.main()
