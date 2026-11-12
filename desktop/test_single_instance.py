"""No visible windows: real Windows kernel objects, fake Tk scheduler."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

for _folder in ('desktop', 'listener'):
    _path = str(Path(__file__).resolve().parents[1] / _folder)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from desktop import launcher


class FakeRoot:
    def __init__(self):
        self.timers = {}
        self.bindings = {}
        self.focused = []
        self.next_id = 0

    def after(self, delay, callback):
        self.next_id += 1
        self.timers[self.next_id] = callback
        return self.next_id

    def after_cancel(self, token):
        self.timers.pop(token, None)

    def bind(self, event, callback, add=None):
        self.bindings[event] = callback

    def deiconify(self):
        self.focused.append('restore')

    def lift(self):
        self.focused.append('lift')

    def focus_force(self):
        self.focused.append('focus')

    def winfo_id(self):
        return 0

    def poll(self):
        callbacks = list(self.timers.values())
        self.timers.clear()
        for callback in callbacks:
            callback()

    def destroy(self):
        event = type('Event', (), {'widget': self})()
        self.bindings['<Destroy>'](event)


class LauncherRoutingTests(unittest.TestCase):
    def test_component_bypasses_singleton(self):
        with patch.object(sys, 'argv', ['app', '--component', 'server']), patch.object(launcher, 'run_component', return_value=19) as run:
            self.assertEqual(launcher.main(), 19)
            run.assert_called_once_with('server', [])

    def test_self_test_does_not_reserve_gui_identity(self):
        from desktop import single_instance
        with patch.object(sys, 'argv', ['app', '--self-test', 'unused.json']), patch.object(single_instance, 'SingleInstance') as reserve, patch('runtime.load_component'), patch.object(launcher.tk, 'Tk', side_effect=RuntimeError('selftest-Tk')):
            with self.assertRaisesRegex(RuntimeError, 'selftest-Tk'):
                launcher.main()
        reserve.assert_not_called()

    def test_non_windows_fallback_creates_no_native_objects(self):
        from desktop import single_instance
        with patch.object(single_instance.sys, 'platform', 'linux'), patch.object(single_instance, '_Windows') as native:
            guard = single_instance.SingleInstance('.')
            root = FakeRoot()
            guard.attach(root)
            self.assertTrue(guard.is_primary)
            self.assertFalse(root.timers)
            root.destroy()
            guard.close()
            native.assert_not_called()

    def test_launcher_success_closes_reservation(self):
        from desktop import single_instance
        from unittest.mock import Mock
        guard = Mock()
        guard.is_primary = True
        with patch.object(sys, 'argv', ['app']), patch.object(single_instance, 'SingleInstance', return_value=guard), patch('runtime.create_update_signal', return_value=None), patch.object(launcher, 'run_launcher', return_value=0) as gui:
            self.assertEqual(launcher.main(), 0)
        gui.assert_called_once_with(None, guard)
        guard.close.assert_called_once()

    def test_launcher_exception_closes_reservation_and_update_signal(self):
        from desktop import single_instance
        from unittest.mock import Mock
        guard, signal = Mock(), Mock()
        guard.is_primary = True
        signal.is_set.return_value = False
        with patch.object(sys, 'argv', ['app']), patch.object(single_instance, 'SingleInstance', return_value=guard), patch('runtime.create_update_signal', return_value=signal), patch.object(launcher, 'run_launcher', side_effect=RuntimeError('startup')):
            with self.assertRaisesRegex(RuntimeError, 'startup'):
                launcher.main()
        guard.close.assert_called_once()
        signal.close.assert_called_once()

    def test_secondary_does_not_create_gui_or_update_signal(self):
        from desktop import single_instance
        from unittest.mock import Mock
        guard = Mock()
        guard.is_primary = False
        with patch.object(sys, 'argv', ['app']), patch.object(single_instance, 'SingleInstance', return_value=guard), patch.object(launcher, 'run_launcher') as gui, patch('runtime.create_update_signal') as update:
            self.assertEqual(launcher.main(), 0)
        gui.assert_not_called()
        update.assert_not_called()
        guard.close.assert_called_once()


@unittest.skipUnless(sys.platform == 'win32', 'Windows kernel integration')
class WindowsSingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='singleton-test-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def child(self, code):
        return subprocess.run([sys.executable, '-c', code, str(self.data)], capture_output=True, text=True, timeout=15)

    def test_real_secondary_signals_startup_then_fake_tk_poll_focuses(self):
        from desktop.single_instance import SingleInstance
        first = SingleInstance(self.data)
        self.addCleanup(first.close)
        self.assertTrue(first.is_primary)
        result = self.child('from desktop.single_instance import SingleInstance; import sys; g=SingleInstance(sys.argv[1]); print(g.is_primary); g.close()')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'False')
        root = FakeRoot()
        first.attach(root)
        root.poll()
        self.assertEqual(root.focused, ['restore', 'lift', 'focus'])
        root.poll()
        self.assertEqual(len(root.focused), 3)
        root.destroy()
        self.assertFalse(root.timers)
        replacement = SingleInstance(self.data)
        self.addCleanup(replacement.close)
        self.assertTrue(replacement.is_primary)

    def test_crashed_process_releases_reservation(self):
        result = self.child('from desktop.single_instance import SingleInstance; import sys,os; g=SingleInstance(sys.argv[1]); print(g.is_primary,flush=True); os._exit(37)')
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(result.stdout.strip(), 'True')
        from desktop.single_instance import SingleInstance
        recovered = SingleInstance(self.data)
        self.addCleanup(recovered.close)
        self.assertTrue(recovered.is_primary)

    def test_canonical_path_identity_and_independent_data(self):
        from desktop.single_instance import SingleInstance
        first = SingleInstance(self.data)
        self.addCleanup(first.close)
        # Mutex ownership is recursive for a single Windows thread, so a
        # repeated launch must be tested in a genuinely separate process.
        result = self.child("from desktop.single_instance import SingleInstance; from pathlib import Path; import sys; p=Path(sys.argv[1]); g=SingleInstance(p/'..'/p.name); print(g.is_primary); g.close()")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'False')
        other = SingleInstance(self.data / 'other')
        self.addCleanup(other.close)
        self.assertTrue(other.is_primary)


if __name__ == '__main__':
    unittest.main()
