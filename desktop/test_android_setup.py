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

PUBLIC_APK = 'https://github.com/alexfduch231-prog/DroidBridge/releases/download/v1.0.9/DroidBridge-1.18-android.apk'


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

    def test_embedded_builder_owns_no_window_and_disposed_callback_is_inert(self):
        import tkinter as tk
        from tkinter import ttk
        root, paired = self.root(), []
        page = android_setup.build_android_setup_page(root, self.data, lambda: paired.append(True))
        self.assertIsInstance(page, ttk.Frame)
        self.assertEqual(page.winfo_manager(), '')
        self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
        page.pack(fill='both', expand=True)
        button(page, 'Уже установлено → подключить к ПК').invoke()
        self.assertEqual(paired, [True])
        self.assertTrue(page.winfo_exists())
        page.dispose()
        page.dispose()
        button(page, 'Уже установлено → подключить к ПК').invoke()
        self.assertEqual(paired, [True])
        self.assertFalse(self.data.exists())

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
        import tkinter as tk
        from tkinter import ttk
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
            canvas = next(w for w in descendants(window) if isinstance(w, tk.Canvas))
            self.assertGreaterEqual(canvas.winfo_rooty(), window.winfo_rooty())
            self.assertLessEqual(canvas.winfo_rooty() + canvas.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())
            for widget in descendants(window):
                # Auto-hidden overflow bars are intentionally unmanaged; real
                # content and controls must still be mapped and reachable.
                if isinstance(widget, ttk.Scrollbar) and not widget.winfo_manager():
                    continue
                self.assertTrue(widget.winfo_ismapped(), str(widget))
                if isinstance(widget, (ttk.Button, ttk.Checkbutton)):
                    self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight(), str(widget))
                    widget.focus_force()
                    window.update()
                    self.assertGreaterEqual(widget.winfo_rooty(), canvas.winfo_rooty(), str(widget))
                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                         canvas.winfo_rooty() + canvas.winfo_height(), str(widget))
            canvas.yview_moveto(1)
            window.update()
            self.assertAlmostEqual(canvas.yview()[1], 1.0)
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
        # Launcher GUI tests exercise onboarding, never a real update-feed request.
        updates = patch('update_manager.start_startup_check')
        updates.start()
        self.addCleanup(updates.stop)
        return importlib.import_module('desktop.launcher')

    def test_regular_startup_embeds_setup_without_windows_or_services(self):
        import tkinter as tk
        launcher = self.launcher()
        seen = []
        def inspect(root):
            try:
                root.update()
                windows = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
                self.assertEqual(windows, [])
                self.assertEqual(root.navigation.current_key, 'connection')
                page = root.navigation.pages['connection']
                button(page, 'Уже установлено → подключить к ПК')
                seen.append('embedded setup')
                root.update_idletasks()
                for w in descendants(root):
                    if w.winfo_toplevel() is not root:
                        continue
                    # Unsupported native chrome deliberately keeps its fallback
                    # titlebar subtree hidden while the standard OS caption stays.
                    titlebar = root.window_chrome.titlebar
                    if not titlebar.winfo_ismapped() and (w is titlebar or str(w).startswith(str(titlebar) + '.')):
                        continue
                    # Canvas content may extend below its clipped viewport; the
                    # launcher resize tests verify scrolling and focus reachability.
                    ancestor = w.master
                    in_scroll_content = False
                    while ancestor is not None and ancestor is not root:
                        if isinstance(ancestor, tk.Canvas):
                            in_scroll_content = True
                            break
                        ancestor = ancestor.master
                    if in_scroll_content:
                        continue
                    # Auto-hiding sidebar scrollbars are intentionally unmanaged
                    # when all navigation controls fit in the viewport.
                    if w.winfo_class() == 'TScrollbar' and not w.winfo_manager():
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
        self.assertEqual(seen, ['embedded setup'])

    def test_optout_persists_when_connection_page_is_explicitly_revisited(self):
        import tkinter as tk
        launcher = self.launcher()
        android_setup.save_dont_show(self.data, True)
        def inspect(root):
            try:
                root.update()
                self.assertFalse(any(isinstance(w, tk.Toplevel) for w in root.winfo_children()))
                root.show_section('screen')
                button(root, 'Подключение').invoke()
                self.assertEqual(root.navigation.current_key, 'connection')
                button(root.navigation.pages['connection'], 'Приложение уже установлено')
                button(root.navigation.pages['connection'], 'Установить приложение Android').invoke()
                button(root.navigation.pages['connection'], 'Уже установлено → подключить к ПК')
                self.assertFalse(any(isinstance(w, tk.Toplevel) for w in root.winfo_children()))
                self.assertFalse(android_setup.should_show_on_startup(self.data))
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data), \
             patch.object(tk.Tk, 'mainloop', inspect):
            self.assertEqual(launcher.main(), 0)

    def test_launcher_onboarding_replaces_page_using_pairing_callback(self):
        import tkinter as tk
        launcher = self.launcher()
        seen = []
        def pair(parent, data_dir, http_port):
            from tkinter import ttk
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in parent.winfo_children()))
            self.assertFalse(any(w.winfo_exists() for w in old_pages))
            seen.append((data_dir, http_port))
            return ttk.Frame(parent)
        old_pages = []
        continuation = []
        def gate(parent, data_dir, on_completed):
            from tkinter import ttk
            self.assertEqual(data_dir, self.data)
            continuation.append(on_completed)
            return ttk.Frame(parent)
        def inspect(root):
            try:
                root.update()
                page = root.navigation.pages['connection']
                old_pages.append(page)
                button(page, 'Уже установлено → подключить к ПК').invoke()
                self.assertEqual(root.navigation.current_key, 'connection')
                self.assertEqual(seen, [], 'Android installation must not bypass the mandatory WoL gate')
                continuation[0]()
                self.assertEqual(seen, [], 'missing completion must still block QR creation')
                self.data.mkdir(parents=True, exist_ok=True)
                (self.data / 'wol_onboarding.json').write_text(json.dumps({
                    'schema': 1, 'adapter_guid': '00000000-0000-0000-0000-000000000001',
                    'bios_manual_ack': True, 'network_compatible': True, 'completed': True}), encoding='utf-8')
                continuation[0]()
                self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data), \
             patch('desktop.wol_onboarding.build_onboarding_page', side_effect=gate), \
             patch('pairing_panel.build_pairing_page', side_effect=pair), patch.object(tk.Tk, 'mainloop', inspect):
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
