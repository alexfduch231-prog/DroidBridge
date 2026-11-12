"""Android onboarding is local, optional, and separate from pairing."""
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from desktop import android_setup
except ImportError:
    android_setup = None

PUBLIC_APK = 'https://github.com/alexfduch231-prog/DroidBridge/releases/download/v1.0.2/DroidBridge-1.14-android.apk'


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(window, text):
    from tkinter import ttk
    return next(w for w in descendants(window)
                if isinstance(w, ttk.Button) and w.cget('text') == text)


class AndroidSetupTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(android_setup, 'local Android onboarding module must exist')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name) / 'data'

    def test_missing_malformed_oversized_or_nonboolean_preference_shows_window(self):
        self.assertTrue(android_setup.should_show_on_startup(self.data))
        self.assertFalse(self.data.exists())
        self.data.mkdir()
        path = self.data / 'android_setup.json'
        for text in ('{bad', '[]', '{}', '{"dont_show":"yes"}',
                     '{"version":true,"dont_show":true}',
                     '{"version":1,"dont_show":true}' + ' ' * 4097,
                     '[' * 1500 + '0' + ']' * 1500):
            with self.subTest(text=text[:50]):
                path.write_text(text, encoding='utf-8')
                self.assertTrue(android_setup.should_show_on_startup(self.data))

    def test_preference_roundtrip_only_writes_own_atomic_config(self):
        self.data.mkdir()
        for name in ('token.txt', 'apps.json', 'media_settings.json'):
            (self.data / name).write_text('untouched')
        android_setup.save_dont_show(self.data, True)
        self.assertFalse(android_setup.should_show_on_startup(self.data))
        self.assertEqual(json.loads((self.data / 'android_setup.json').read_text()),
                         {'version': 1, 'dont_show': True})
        android_setup.save_dont_show(self.data, False)
        self.assertTrue(android_setup.should_show_on_startup(self.data))
        self.assertEqual(sorted(p.name for p in self.data.iterdir()),
                         ['android_setup.json', 'apps.json', 'media_settings.json', 'token.txt'])
        for name in ('token.txt', 'apps.json', 'media_settings.json'):
            self.assertEqual((self.data / name).read_text(), 'untouched')

    def test_atomic_replace_failure_preserves_previous_and_removes_temp(self):
        android_setup.save_dont_show(self.data, True)
        with patch.object(android_setup.os, 'replace', side_effect=OSError('failure')):
            with self.assertRaises(OSError):
                android_setup.save_dont_show(self.data, False)
        self.assertFalse(android_setup.should_show_on_startup(self.data))
        self.assertEqual([p.name for p in self.data.iterdir()], ['android_setup.json'])

    def root(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        return root

    def test_duplicate_window_is_reused_and_close_never_pairs(self):
        root, paired = self.root(), []
        window = android_setup.show_android_setup(root, self.data, lambda: paired.append(True))
        same = android_setup.show_android_setup(root, self.data, lambda: paired.append(False))
        self.assertIs(same, window)
        window.tk.call(window.protocol('WM_DELETE_WINDOW'))
        self.assertEqual(paired, [])
        self.assertFalse(self.data.exists())
        new = android_setup.show_android_setup(root, self.data, lambda: paired.append(True))
        button(new, 'Уже установлено → подключить к ПК').invoke()
        self.assertEqual(paired, [True])
        self.assertFalse(new.winfo_exists())

    def test_install_qr_encodes_only_public_url_and_pairs_only_on_explicit_action(self):
        import qrcode
        root, paired, payloads = self.root(), [], []
        root.deiconify()
        root.update()
        real_make = qrcode.make
        def make(payload, **kwargs):
            payloads.append(payload)
            return real_make(payload, **kwargs)
        with patch('qrcode.make', side_effect=make), patch('webbrowser.open') as opened:
            window = android_setup.show_android_setup(root, self.data, lambda: paired.append(True))
            self.assertEqual(payloads, [])
            button(window, 'Установить на телефон').invoke()
            root.update()
            root.update_idletasks()
            self.assertEqual(payloads, [PUBLIC_APK])
            self.assertEqual(paired, [])
            opened.assert_not_called()
            labels = ' '.join(str(w.cget('text')) for w in descendants(window)
                              if 'text' in w.keys())
            self.assertIn('не QR сопряжения', labels)
            self.assertIn('неизвестных', labels)
            self.assertNotIn('\\n', labels)
            for widget in descendants(window):
                self.assertTrue(widget.winfo_ismapped(), str(widget))
                self.assertGreaterEqual(widget.winfo_rootx(), window.winfo_rootx(), str(widget))
                self.assertGreaterEqual(widget.winfo_rooty(), window.winfo_rooty(), str(widget))
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                     window.winfo_rootx() + window.winfo_width(), str(widget))
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height(), str(widget))
                self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight(), str(widget))
            button(window, 'Скопировать ссылку APK').invoke()
            self.assertEqual(window.clipboard_get(), PUBLIC_APK)
            button(window, 'Открыть ссылку APK').invoke()
            opened.assert_called_once_with(PUBLIC_APK)
            button(window, 'Установлено → подключить к ПК').invoke()
        self.assertEqual(paired, [True])
        self.assertFalse(self.data.exists())

    def test_checkbox_persists_and_manual_reopen_is_always_available(self):
        from tkinter import ttk
        root = self.root()
        window = android_setup.show_android_setup(root, self.data, lambda: None)
        check = next(w for w in descendants(window) if isinstance(w, ttk.Checkbutton))
        check.invoke()
        self.assertFalse(android_setup.should_show_on_startup(self.data))
        window.destroy()
        window = android_setup.show_android_setup(root, self.data, lambda: None)
        check = next(w for w in descendants(window) if isinstance(w, ttk.Checkbutton))
        self.assertTrue(check.instate(['selected']))
        check.invoke()
        self.assertTrue(android_setup.should_show_on_startup(self.data))

    def launcher(self):
        path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, path)
        self.addCleanup(lambda: sys.path.remove(path))
        return importlib.import_module('desktop.launcher')

    def test_regular_startup_shows_optional_window_but_never_starts_services(self):
        import tkinter as tk
        launcher = self.launcher()
        seen = []
        def inspect(root):
            try:
                root.update()
                windows = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
                self.assertEqual(len(windows), 1)
                seen.append(windows[0].title())
                root.update_idletasks()
                for w in descendants(root):
                    if w.winfo_toplevel() is not root:
                        continue
                    self.assertTrue(w.winfo_ismapped(), str(w))
                    self.assertGreaterEqual(w.winfo_rootx(), root.winfo_rootx(), str(w))
                    self.assertGreaterEqual(w.winfo_rooty(), root.winfo_rooty(), str(w))
                    self.assertLessEqual(w.winfo_rootx() + w.winfo_width(),
                                         root.winfo_rootx() + root.winfo_width(), str(w))
                    self.assertLessEqual(w.winfo_rooty() + w.winfo_height(),
                                         root.winfo_rooty() + root.winfo_height(), str(w))
                    self.assertGreaterEqual(w.winfo_height(), w.winfo_reqheight(), str(w))
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data), \
             patch.object(launcher, 'start_child', side_effect=AssertionError('no service startup')), \
             patch.object(socket.socket, 'bind', side_effect=AssertionError('no listener')), \
             patch.object(tk.Tk, 'mainloop', inspect):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(seen, ['DroidBridge — приложение на телефон'])

    def test_optout_suppresses_startup_but_repeated_button_opens_window(self):
        import tkinter as tk
        launcher = self.launcher()
        android_setup.save_dont_show(self.data, True)
        def inspect(root):
            try:
                root.update()
                self.assertFalse(any(isinstance(w, tk.Toplevel) for w in root.winfo_children()))
                button(root, 'Приложение на телефон / подключить').invoke()
                self.assertEqual(len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]), 1)
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data), \
             patch.object(tk.Tk, 'mainloop', inspect):
            self.assertEqual(launcher.main(), 0)

    def test_launcher_onboarding_uses_existing_pairing_callback_after_closing(self):
        import tkinter as tk
        launcher = self.launcher()
        seen = []
        def pair(parent, data_dir, http_port):
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in parent.winfo_children()))
            seen.append((data_dir, http_port))
        def inspect(root):
            try:
                root.update()
                window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                button(window, 'Уже установлено → подключить к ПК').invoke()
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data), \
             patch('pairing_panel.show_pairing', side_effect=pair), patch.object(tk.Tk, 'mainloop', inspect):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(seen, [(self.data, 8765)])

    def test_import_is_lazy_and_does_not_load_gui_or_network_dependencies(self):
        result = subprocess.run([sys.executable, '-c',
            'import sys; from desktop import android_setup; '
            'assert not any(name in sys.modules for name in '
            '("tkinter", "qrcode", "pairing_panel", "webbrowser"))'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_component_mode_and_selftest_do_not_show_onboarding_or_launch_processes(self):
        launcher = self.launcher()
        output = self.data.parent / 'selftest.json'
        with patch.object(android_setup, 'show_android_setup', side_effect=AssertionError('no onboarding')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('no child')), \
             patch.object(socket.socket, 'bind', side_effect=AssertionError('no sockets')):
            with patch.object(sys, 'argv', ['launcher', '--component', 'viewer']), \
                 patch.object(launcher, 'run_component', return_value=7) as run:
                self.assertEqual(launcher.main(), 7)
                run.assert_called_once_with('viewer', [])
            with patch.object(sys, 'argv', ['launcher', '--self-test', str(output)]):
                self.assertEqual(launcher.main(), 0)
        report = json.loads(output.read_text())
        self.assertTrue(report['ok'])
        self.assertIn('android_setup', report['components_imported'])


if __name__ == '__main__':
    unittest.main()
