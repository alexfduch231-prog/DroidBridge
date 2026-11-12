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


class ManualCheckTests(unittest.TestCase):
    class Root:
        def __init__(self):
            self.callbacks = {}
            self.bindings = {}
            self.serial = 0
        def bind(self, event, callback, add=None):
            self.bindings['destroy'] = callback
            return 'destroy'
        def unbind(self, event, token):
            self.bindings.pop(token, None)
        def after(self, delay, callback):
            self.serial += 1
            self.callbacks[self.serial] = callback
            return self.serial
        def after_cancel(self, token):
            self.callbacks.pop(token, None)
        def pump(self):
            for token, callback in list(self.callbacks.items()):
                self.callbacks.pop(token, None)
                callback()

    def setUp(self):
        from unittest.mock import patch
        import update_manager as m
        self.m = m
        self.root = self.Root()
        self.threads = []
        class Thread:
            def __init__(thread, *, target, **kwargs):
                self.threads.append(target)
            def start(thread):
                pass
        self.patch = patch.object(m.threading, 'Thread', Thread)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_direct_drain_cancels_previous_timer_instead_of_orphaning_it(self):
        from unittest.mock import patch
        with patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '1.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=False), \
                patch('tkinter.messagebox.showinfo'):
            controller = self.m.start_manual_check(self.root, '.', None)
            self.threads.pop()()
            controller._drain()
            self.assertFalse(self.root.callbacks)

    def test_manual_latest_feedback_and_retry_without_polling_leak(self):
        from unittest.mock import patch
        with patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '1.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=False), \
                patch('tkinter.messagebox.showinfo') as info:
            first = self.m.start_manual_check(self.root, '.', None)
            self.threads.pop()()
            self.root.pump()
            self.assertIn('актуаль', info.call_args.args[1])
            self.assertFalse(self.root.callbacks)
            self.assertFalse(self.root.bindings)
            self.assertFalse(first.alive)
            self.assertIsNot(self.m.start_manual_check(self.root, '.', None), first)

    def test_manual_offline_and_verification_errors_are_safe(self):
        from unittest.mock import patch
        for error, fragment in ((OSError('secret-token'), 'соединение'),
                                (ValueError('private signature details'), 'провер')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(self.m, 'check_manifest', side_effect=error), \
                    patch('tkinter.messagebox.showerror') as feedback:
                self.m.start_manual_check(self.root, '.', None)
                self.threads.pop()()
                self.root.pump()
                text = feedback.call_args.args[1]
                self.assertIn(fragment, text.lower())
                self.assertNotIn(str(error), text)
                self.assertFalse(self.root.callbacks)

    def test_manual_dedup_and_startup_overlap(self):
        from unittest.mock import patch
        with patch.object(self.m, '_started', False), \
                patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '1.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=False), \
                patch('tkinter.messagebox.showinfo') as info:
            startup = self.m.start_startup_check(self.root, '.', None)
            self.assertIs(self.m.start_manual_check(self.root, '.', None), startup)
            self.assertIs(self.m.start_manual_check(self.root, '.', None), startup)
            self.assertEqual(len(self.threads), 1)
            self.threads.pop()()
            self.root.pump()
            info.assert_called_once()
            self.assertIsNone(self.m.start_startup_check(self.root, '.', None))
            self.assertIsNotNone(self.m.start_manual_check(self.root, '.', None))

    def test_manual_new_version_uses_existing_offer_and_keeps_dedup(self):
        from unittest.mock import patch
        manifest = {'windows': {'version': '99.0.0'}}
        def offer(controller, value):
            self.assertIs(value, manifest)
            controller.window = object()
        with patch.object(self.m, 'check_manifest', return_value=manifest), \
                patch.object(self.m, 'is_newer', return_value=True), \
                patch.object(self.m.UpdateController, '_offer', offer):
            controller = self.m.start_manual_check(self.root, '.', None)
            self.threads.pop()()
            self.root.pump()
            self.assertIs(self.m.start_manual_check(self.root, '.', None), controller)
            self.assertFalse(self.root.callbacks)
            self.assertEqual(len(self.threads), 0)

    def test_offer_dismiss_releases_controller_for_retry(self):
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '99.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=True):
            controller = self.m.start_manual_check(root, '.', None)
            self.threads.pop()()
            controller._drain()
            dialog = controller.window
            row = next(child for child in dialog.winfo_children() if isinstance(child, ttk.Frame))
            next(child for child in row.winfo_children() if child.cget('text') == 'Not now').invoke()
            self.assertIsNone(controller.window)
            self.assertFalse(controller.alive)
            self.assertIsNot(self.m.start_manual_check(root, '.', None), controller)

    def test_manual_uses_signed_manifest_and_persisted_sequence(self):
        from datetime import datetime, timezone
        from test_update_protocol import FIXTURE
        from update_protocol import SequenceState
        from unittest.mock import patch
        real_check = self.m.check_manifest
        for maximum, expected_offer in ((0, True), (2, False)):
            with self.subTest(maximum=maximum), tempfile.TemporaryDirectory() as directory, \
                    patch.object(self.m, 'check_manifest', side_effect=lambda path: real_check(path, opener=lambda url: io.BytesIO(FIXTURE), now=datetime(2026, 11, 13, tzinfo=timezone.utc))), \
                    patch.object(self.m, 'is_newer', return_value=True), \
                    patch.object(self.m.UpdateController, '_offer') as offer, \
                    patch('tkinter.messagebox.showerror') as error:
                if maximum:
                    SequenceState(Path(directory)).accept(maximum)
                self.m.start_manual_check(self.root, directory, None)
                self.threads.pop()()
                self.root.pump()
                self.assertEqual(offer.called, expected_offer)
                self.assertEqual(error.called, not expected_offer)
                self.assertEqual(SequenceState(Path(directory)).maximum(), maximum or 1)

    def test_source_offer_only_opens_release_page_after_explicit_click(self):
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '99.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=True), \
                patch.object(self.m.webbrowser, 'open') as browser, \
                patch.object(self.m, 'download_asset') as download:
            controller = self.m.start_manual_check(root, '.', None)
            self.threads.pop()()
            controller._drain()
            browser.assert_not_called()
            dialog = controller.window
            row = next(child for child in dialog.winfo_children() if isinstance(child, ttk.Frame))
            next(child for child in row.winfo_children() if child.cget('text') == 'Update').invoke()
            browser.assert_called_once_with('https://github.com/alexfduch231-prog/DroidBridge/releases/latest')
            download.assert_not_called()
            self.assertIsNone(controller.window)
            self.assertFalse(controller.alive)

    def test_manual_rejects_bad_signed_manifest_without_fallback(self):
        from unittest.mock import patch
        real_check = self.m.check_manifest
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.m, 'check_manifest', side_effect=lambda path: real_check(path, opener=lambda url: io.BytesIO(b'{"signature":"bad"}'))), \
                patch.object(self.m.UpdateController, '_offer') as offer, \
                patch('tkinter.messagebox.showerror') as error, \
                patch.object(self.m.webbrowser, 'open') as browser:
            self.m.start_manual_check(self.root, directory, None)
            self.threads.pop()()
            self.root.pump()
            error.assert_called_once()
            offer.assert_not_called()
            browser.assert_not_called()
            self.assertFalse(list(Path(directory).iterdir()))

    def test_download_keeps_single_job_and_releases_after_cancel(self):
        import sys
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        from datetime import datetime, timezone
        from test_update_protocol import FIXTURE
        from update_protocol import verify_manifest
        manifest = verify_manifest(FIXTURE, now=datetime(2026, 11, 13, tzinfo=timezone.utc))
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.m, 'check_manifest', return_value=manifest), \
                patch.object(self.m, 'is_newer', return_value=True), \
                patch.object(sys, 'frozen', True, create=True), \
                patch('tkinter.messagebox.askyesno', return_value=True), \
                patch.object(self.m, 'download_asset', side_effect=self.m.Cancelled()), \
                patch('tkinter.messagebox.showerror') as error:
            controller = self.m.start_manual_check(root, directory, None)
            self.threads.pop()()
            controller._drain()
            row = next(child for child in controller.window.winfo_children() if isinstance(child, ttk.Frame))
            next(child for child in row.winfo_children() if child.cget('text') == 'Update').invoke()
            self.assertIs(self.m.start_manual_check(root, directory, None), controller)
            self.assertEqual(len(self.threads), 1)
            self.assertIsNotNone(controller.timer)
            controller.cancel.set()
            self.threads.pop()()
            controller._drain()
            self.assertFalse(controller.alive)
            self.assertIsNone(controller.window)
            error.assert_not_called()

    def test_root_destroy_cancels_pending_work_and_unbinds(self):
        from unittest.mock import patch
        with patch.object(self.m, 'check_manifest', return_value={'windows': {'version': '1.0.0'}}), \
                patch.object(self.m, 'is_newer', return_value=False), \
                patch('tkinter.messagebox.showinfo') as info:
            controller = self.m.start_manual_check(self.root, '.', None)
            controller._destroy(type('Event', (), {'widget': self.root})())
            self.threads.pop()()
            self.root.pump()
            self.assertTrue(controller.cancel.is_set())
            self.assertFalse(controller.alive)
            self.assertFalse(self.root.callbacks)
            self.assertFalse(self.root.bindings)
            info.assert_not_called()


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
