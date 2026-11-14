"""Real Tk checks for shared Android styling and launcher resizing."""
import importlib
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        # Legacy light presentation assertions must not depend on the user's OS.
        detector = patch('desktop.theme.system_theme', return_value='light')
        detector.start()
        self.addCleanup(detector.stop)

    def test_shared_theme_renders_android_palette_and_button_states(self):
        # Missing theme application would leave platform-dependent grey controls.
        theme = importlib.import_module('desktop.theme')
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_theme(root)
        style = ttk.Style(root)
        self.assertEqual(style.theme_use(), 'clam')
        self.assertEqual(root.cget('background').lower(), '#f7f7f8')
        self.assertEqual(style.lookup('DB.Primary.TButton', 'background'), '#EEEEF0')
        self.assertEqual(style.lookup('DB.Primary.TButton', 'foreground'), '#202024')
        self.assertNotEqual(style.lookup('DB.Primary.TButton', 'background', ('disabled',)), '#EEEEF0')
        panel = theme.card(root)
        panel.pack()
        self.assertEqual(style.lookup(panel.cget('style'), 'background').lower(), root.cget('background').lower())
        self.assertEqual(style.lookup('DB.Muted.TLabel', 'foreground'), '#606068')
        theme.apply_theme(root)  # Reapplying for an owned Toplevel must be safe.
        window = tk.Toplevel(root)
        theme.apply_theme(window)
        self.assertEqual(window.cget('background').lower(), '#f7f7f8')

    def test_window_icon_uses_source_or_frozen_assets_for_roots_and_dialogs(self):
        theme = importlib.import_module('desktop.theme')
        root = tk.Tk()
        self.addCleanup(root.destroy)
        window = tk.Toplevel(root)
        source_icon = Path(theme.__file__).resolve().parents[1] / 'assets' / 'droidbridge.ico'
        for target in (root, window):
            with self.subTest(window=type(target).__name__), patch.object(target, 'iconbitmap') as assigned:
                theme.apply_theme(target)
                assigned.assert_called_once_with(str(source_icon))
        with tempfile.TemporaryDirectory() as bundled:
            with patch.object(sys, '_MEIPASS', bundled, create=True), \
                 patch.object(window, 'iconbitmap') as assigned:
                theme.apply_theme(window)
                assigned.assert_called_once_with(str(Path(bundled) / 'assets' / 'droidbridge.ico'))

    def test_missing_or_unsupported_icon_does_not_break_window_styling(self):
        theme = importlib.import_module('desktop.theme')
        root = tk.Tk()
        self.addCleanup(root.destroy)
        with patch.object(root, 'iconbitmap', side_effect=tk.TclError('missing or unsupported icon')):
            theme.apply_theme(root)
        self.assertEqual(root.cget('background').lower(), '#f7f7f8')
        self.assertEqual(ttk.Style(root).theme_use(), 'clam')

    def test_installed_ui_font_preference_and_fallback_are_root_local(self):
        theme = importlib.import_module('desktop.theme')
        root = tk.Tk()
        self.addCleanup(root.destroy)
        fallback = theme.font.nametofont('TkDefaultFont', root=root).actual('family')
        for available, expected in (
                (('Segoe UI', 'segoe ui variable text', 'Segoe UI Variable'), 'segoe ui variable text'),
                (('Segoe UI', 'Segoe UI Variable'), 'Segoe UI Variable'),
                (('Segoe UI',), 'Segoe UI'),
                (('Arial',), fallback)):
            with self.subTest(available=available):
                if hasattr(root, '_droidbridge_font'):
                    del root._droidbridge_font
                with patch.object(theme.font, 'families', return_value=available):
                    self.assertEqual(theme.font_family(root), expected)
                    window = tk.Toplevel(root)
                    self.assertEqual(theme.font_family(window), expected)
                    window.destroy()
        # The chosen face also reaches widget styles, not only the helper.
        theme.apply_theme(root)
        self.assertEqual(root.tk.splitlist(ttk.Style(root).lookup('TButton', 'font'))[0], fallback)

    def test_launcher_cards_resize_and_scroll_without_starting_network_or_children(self):
        # Fixed minimum sizing or an unscrollable body would hide actions at 800x600.
        desktop_path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, desktop_path)
        self.addCleanup(lambda: sys.path.remove(desktop_path))
        launcher = importlib.import_module('desktop.launcher')
        with tempfile.TemporaryDirectory() as isolated:
            def inspect(root):
                try:
                    root.update()
                    self.assertEqual((root.winfo_width(), root.winfo_height()), (1040, 780))
                    self.assertEqual(root.navigation.current_key, 'connection')
                    nav = next(w for w in descendants(root) if isinstance(w, ttk.Button) and ''.join(str(w.cget('text')).split()) == 'Подключение')
                    self.assertGreaterEqual(nav.master.winfo_width(), 196)
                    self.assertLessEqual(nav.master.winfo_width(), int(root.winfo_width() * .45))
                    self.assertLessEqual(nav.winfo_reqwidth(), nav.winfo_width())
                    from update_protocol import CURRENT_VERSION
                    version = next(w for w in descendants(nav.master) if isinstance(w, ttk.Label) and w.cget('text') == 'PConDistance ' + CURRENT_VERSION)
                    manual_update = next(w for w in descendants(nav.master) if isinstance(w, ttk.Button) and ''.join(str(w.cget('text')).split()) == 'Проверитьобновления')
                    manual_update.invoke()
                    manual_check.assert_called_once_with(root, Path(isolated), None)
                    self.assertTrue(nav.cget('image'), 'navigation needs restrained line icons')
                    self.assertEqual(nav.cget('style'), 'DB.Nav.Selected.TButton')
                    root.show_section('screen')
                    self.assertEqual(nav.cget('style'), 'DB.Nav.TButton')
                    root.show_section('connection')
                    summaries = [w for w in descendants(root) if isinstance(w, ttk.Label) and w.cget('textvariable') == str(root.wol_status)]
                    self.assertTrue(summaries)
                    self.assertTrue(all(str(w).startswith(str(root.navigation) + '.') for w in summaries), 'WoL guidance belongs to connection content, not a global banner')
                    self.assertEqual(len(root._navigation_icons), 6)
                    for image in root._navigation_icons.values():
                        self.assertEqual((image.width(), image.height()), (12, 12))
                    for size, scaling in (('940x760', 1.33), ('800x600', 2.0), ('800x600', 3.0)):
                        root.tk.call('tk', 'scaling', scaling)
                        root.geometry(size)
                        root.update()
                        manual_update.event_generate('<FocusIn>')
                        root.update()
                        for footer_widget in (version, manual_update):
                            self.assertTrue(footer_widget.winfo_ismapped())
                            self.assertGreaterEqual(footer_widget.winfo_rooty(), root.winfo_rooty())
                            self.assertLessEqual(footer_widget.winfo_rooty() + footer_widget.winfo_height(), root.winfo_rooty() + root.winfo_height())
                        for title in ('Подключение', 'Экран телефона', 'Программы', 'Приём файлов', 'Включение ПК', 'Настройки'):
                            button = next(w for w in descendants(root) if isinstance(w, ttk.Button) and ''.join(str(w.cget('text')).split()) == ''.join(title.split()))
                            button.event_generate('<FocusIn>')
                            root.update()
                            self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width(), (title, scaling, button.cget('text'), ttk.Style(button).lookup(button.cget('style'), 'font'), ttk.Style(button).lookup(button.cget('style'), 'padding'), button.tk.call('font', 'measure', ttk.Style(button).lookup(button.cget('style'), 'font'), button.cget('text')), button.master.winfo_width(), button.master.master.winfo_width()))
                            self.assertGreaterEqual(button.winfo_rootx(), root.winfo_rootx())
                            self.assertGreaterEqual(button.winfo_rooty(), root.winfo_rooty())
                            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), root.winfo_rootx() + root.winfo_width())
                            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), root.winfo_rooty() + root.winfo_height())
                        # Every section replaces the same page host, never a tool window.
                        for key in ('screen', 'apps', 'uploads', 'settings', 'connection'):
                            root.show_section(key)
                            root.update()
                            self.assertEqual(root.navigation.current_key, key)
                            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
                            canvas = next(w for w in descendants(root.navigation) if isinstance(w, tk.Canvas))
                            controls = [w for w in descendants(canvas) if isinstance(w, (ttk.Button, ttk.Entry, ttk.Checkbutton))]
                            self.assertTrue(controls)
                            for widget in controls:
                                widget.event_generate('<FocusIn>')
                                root.update()
                                self.assertGreaterEqual(widget.winfo_rooty(), canvas.winfo_rooty())
                                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), canvas.winfo_rooty() + canvas.winfo_height())
                                diagnostic = (key, str(widget), widget.cget('text') if 'text' in widget.keys() else '', widget.winfo_width(), canvas.winfo_width())
                                self.assertGreaterEqual(widget.winfo_rootx(), canvas.winfo_rootx(), diagnostic)
                                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), canvas.winfo_rootx() + canvas.winfo_width(), diagnostic)
                finally:
                    root.destroy()
            with patch.object(sys, 'argv', ['launcher']), \
                 patch.object(launcher, 'data_directory', return_value=Path(isolated)), \
                 patch('runtime.create_update_signal', return_value=None), \
                 patch('android_setup.should_show_on_startup', return_value=False), \
                 patch('update_manager.start_startup_check'), \
                  patch('update_manager.start_manual_check', create=True) as manual_check, \
                 patch.object(launcher, 'start_child', side_effect=AssertionError('no child startup')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('no network')), \
                 patch.object(socket.socket, 'bind', side_effect=AssertionError('no listener')), \
                 patch.object(tk.Tk, 'mainloop', inspect):
                self.assertEqual(launcher.main(), 0)


if __name__ == '__main__':
    unittest.main()
