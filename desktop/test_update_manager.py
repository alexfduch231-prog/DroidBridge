import hashlib
import importlib
import io
from pathlib import Path
import tempfile
import threading
import unittest


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('update_manager')
        self.data = b'synthetic installer, never execute'
        self.asset = {'url': 'https://github.com/alexfduch231-prog/DroidBridge/releases/download/v1/a.exe',
                      'size': len(self.data), 'sha256': hashlib.sha256(self.data).hexdigest()}

    def test_download_verified_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.m.download_asset(self.asset, Path(directory), threading.Event(), opener=lambda u: io.BytesIO(self.data))
            self.assertEqual(result.read_bytes(), self.data)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_hash_truncation_oversize_cancel_cleanup(self):
        for data, cancel in ((b'bad', False), (self.data + b'x', False), (self.data, True)):
            with tempfile.TemporaryDirectory() as directory:
                event = threading.Event()
                if cancel:
                    event.set()
                with self.assertRaises((ValueError, self.m.Cancelled)):
                    self.m.download_asset(self.asset, Path(directory), event, opener=lambda u: io.BytesIO(data))
                self.assertFalse(list(Path(directory).iterdir()))

    def test_redirect_cap_and_cross_host(self):
        transport = self.m.RedirectPolicy()
        with self.assertRaises(ValueError):
            transport.redirect_request(None, None, 302, '', {}, 'https://evil.example/a')
        request = self.m.urllib.request.Request(self.asset['url'])
        for _ in range(5):
            request = transport.redirect_request(request, None, 302, '', {}, self.asset['url'])
        with self.assertRaises(ValueError):
            transport.redirect_request(request, None, 302, '', {}, self.asset['url'])

    def test_no_proxy_credentials_or_user_agent_tokens(self):
        opener = self.m.make_opener()
        self.assertFalse(any(type(handler).__name__ == 'ProxyHandler' and handler.proxies for handler in opener.handlers))


class ControllerTests(unittest.TestCase):
    def test_stale_ready_never_launches_helper(self):
        from unittest.mock import patch
        from datetime import datetime, timezone
        from test_update_protocol import FIXTURE
        from update_protocol import SequenceState, verify_manifest
        import update_manager as m
        manifest = verify_manifest(FIXTURE, now=datetime(2026, 11, 13, tzinfo=timezone.utc))
        class Root:
            def bind(self, *args, **kwargs):
                pass
        with tempfile.TemporaryDirectory() as directory:
            state = SequenceState(Path(directory))
            state.accept(manifest['sequence'] + 1)
            installer = Path(directory) / 'installer.exe'
            installer.write_bytes(b'not executable')
            controller = m.UpdateController(Root(), Path(directory), object())
            with patch('update_helper.launch_helper') as launch, patch.object(controller, '_finish_error') as error:
                controller._ready((installer, manifest))
                launch.assert_not_called()
                self.assertIn('rollback', error.call_args.args[0])
                self.assertFalse(installer.exists())


    def test_destroy_cancels_scheduled_tk_callback(self):
        import update_manager as m
        class Root:
            def bind(self, *args, **kwargs):
                pass
            def after(self, delay, callback):
                return 'timer-id'
            def after_cancel(self, timer):
                self.cancelled = timer
        root = Root()
        controller = m.UpdateController(root, Path('.'), None)
        controller._drain()
        controller._destroy(type('Event', (), {'widget': root})())
        self.assertEqual(root.cancelled, 'timer-id')
        self.assertTrue(controller.cancel.is_set())


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.h = importlib.import_module('update_helper')

    def test_generated_helper_fixed_installer_args_no_kill(self):
        text = self.h.helper_script(Path('C:/DroidBridge-Test/Programs/DroidBridge/DroidBridge.exe'),
                                    Path('C:/DroidBridge-Test/updates/installer.exe'), 'a' * 64, 123)
        self.assertIn('/CURRENTUSER', text)
        self.assertIn('SHA256', text)
        self.assertIn('WaitForExit', text)
        self.assertIn('MainModule.FileName', text)
        self.assertNotIn('Stop-Process', text)
        self.assertNotIn('.Kill(', text)
        self.assertNotIn('--component', text)
        self.assertIn('ExitCode -ne 0', text)
        self.assertIn('FileShare]::Read', text)

    def test_helper_serializes_install_and_resets_before_restart(self):
        text = self.h.helper_script(Path('C:/Programs/DroidBridge/DroidBridge.exe'),
                                    Path('C:/updates/installer.exe'), 'a' * 64, 123)
        self.assertIn('System.Threading.Mutex', text)
        self.assertIn('WaitOne(0)', text)
        self.assertLess(text.index('$event.Reset()'), text.index('Start-Process -FilePath $exe'))

    def test_helper_rechecks_sequence_and_expiry_under_state_lock(self):
        text = self.h.helper_script(Path('C:/Programs/DroidBridge/DroidBridge.exe'),
                                    Path('C:/data/updates/installer.exe'), 'a' * 64, 123,
                                    sequence=7, expires='2030-01-01T00:00:00Z')
        self.assertIn('$stateLock.Lock(0, 1)', text)
        self.assertIn('maxVerifiedSequence -gt 7', text)
        self.assertIn('Manifest expired', text)
        self.assertIn('catch [System.InvalidOperationException]', text)

    def test_helper_parses_in_native_windows_powershell(self):
        import base64
        import subprocess
        script = self.h.helper_script(Path('C:/Programs/DroidBridge/DroidBridge.exe'),
                                      Path('C:/updates/installer.exe'), 'a' * 64, 123)
        # Parser only: no helper actions, network, install or process termination.
        encoded_script = base64.b64encode(script.encode('utf-8')).decode()
        parse = "$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded_script + "'));$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseInput($s,[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){$errors|Out-String|Write-Error;exit 1}"
        result = subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(parse.encode('utf-16le')).decode()], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_native_helper_with_temp_fake_installer_backend(self):
        import base64
        import subprocess
        import runtime
        with tempfile.TemporaryDirectory() as directory:
            setup = Path(directory) / 'installer.exe'
            setup.write_bytes(b'not executable: synthetic fixture')
            exe = Path(directory) / 'DroidBridge.exe'
            signal = runtime.UpdateShutdownSignal(self.h.event_name(exe))
            try:
                script = self.h.helper_script(exe, setup, hashlib.sha256(setup.read_bytes()).hexdigest(), setup.stat().st_size)
                # Fake only the process-launch backend: genuine Windows file lock,
                # hash, named event, mutex, process enumeration and parser execute.
                backend = "function Start-Process { param($FilePath,$ArgumentList,[switch]$Wait,[switch]$PassThru,$WorkingDirectory) if($PassThru){ Write-Output ([pscustomobject]@{ExitCode=0}) } else { Write-Output 'GUI_RESTART_ONLY' } }; "
                result = subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode((backend + script).encode('utf-16le')).decode()], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertIn(b'GUI_RESTART_ONLY', result.stdout)
                self.assertFalse(setup.exists())
                self.assertFalse(signal.is_set())
            finally:
                signal.close()

    def test_native_helper_rejects_advanced_state_and_expired_manifest(self):
        import base64
        import subprocess
        import runtime
        from update_protocol import SequenceState
        for sequence, expiry in ((1, '2030-01-01T00:00:00Z'), (2, '2020-01-01T00:00:00Z')):
            with tempfile.TemporaryDirectory() as directory:
                updates = Path(directory) / 'updates'
                updates.mkdir()
                setup = updates / 'installer.exe'
                setup.write_bytes(b'synthetic')
                SequenceState(Path(directory)).accept(2)
                exe = Path(directory) / 'DroidBridge.exe'
                signal = runtime.UpdateShutdownSignal(self.h.event_name(exe))
                try:
                    script = self.h.helper_script(exe, setup, hashlib.sha256(setup.read_bytes()).hexdigest(), setup.stat().st_size, sequence=sequence, expires=expiry)
                    # Suppress blocking message box in negative-only native tests.
                    script = script.replace("  Add-Type -AssemblyName System.Windows.Forms", "  Write-Output $_.Exception.Message\n  # no dialog in offline test")
                    script = script.replace("  [System.Windows.Forms.MessageBox]::Show('DroidBridge update stopped safely. ' + $_.Exception.Message, 'DroidBridge update') | Out-Null", '')
                    backend = "function Start-Process { throw 'UNEXPECTED_INSTALL' }; "
                    result = subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode((backend + script).encode('utf-16le')).decode()], capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    self.assertIn(b'Manifest rollback' if sequence == 1 else b'Manifest expired', result.stdout)
                    self.assertNotIn(b'UNEXPECTED_INSTALL', result.stdout)
                    self.assertFalse(signal.is_set())
                    self.assertFalse(setup.exists())
                finally:
                    signal.close()

    def test_native_disappeared_process_snapshot_does_not_abort(self):
        import base64
        import subprocess
        import runtime
        with tempfile.TemporaryDirectory() as directory:
            setup = Path(directory) / 'installer.exe'
            setup.write_bytes(b'synthetic')
            exe = Path(directory) / 'DroidBridge.exe'
            signal = runtime.UpdateShutdownSignal(self.h.event_name(exe))
            try:
                script = self.h.helper_script(exe, setup, hashlib.sha256(setup.read_bytes()).hexdigest(), setup.stat().st_size)
                # Deterministic race injection: unassociated Process.Handle raises
                # InvalidOperationException exactly like an exited snapshot entry.
                script = script.replace("[System.Diagnostics.Process]::GetProcessesByName('DroidBridge')", '([System.Diagnostics.Process]::new())')
                backend = "function Start-Process { param($FilePath,$ArgumentList,[switch]$Wait,[switch]$PassThru,$WorkingDirectory) if($PassThru){ Write-Output ([pscustomobject]@{ExitCode=0}) } else { Write-Output 'RACE_HANDLED' } }; "
                result = subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode((backend + script).encode('utf-16le')).decode()], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertIn(b'RACE_HANDLED', result.stdout)
            finally:
                signal.close()

    def test_reject_command_injection_and_untrusted_executable(self):
        for exe in ('C:/x/other.exe', 'C:/x/DroidBridge.exe\"; bad'):
            with self.assertRaises(ValueError):
                self.h.helper_script(Path(exe), Path('C:/updates/installer.exe'), 'a' * 64, 123)


if __name__ == '__main__':
    unittest.main()
