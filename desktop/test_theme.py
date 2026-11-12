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
    def test_shared_theme_renders_android_palette_and_button_states(self):
        # Missing theme application would leave platform-dependent grey controls.
        theme = importlib.import_module('desktop.theme')
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_theme(root)
        style = ttk.Style(root)
        self.assertEqual(style.theme_use(), 'clam')
        self.assertEqual(root.cget('background').lower(), '#f1f3f8')
        self.assertEqual(style.lookup('DB.Primary.TButton', 'background'), '#1A63E7')
        self.assertNotEqual(style.lookup('DB.Primary.TButton', 'background', ('disabled',)), '#1A63E7')
        panel = theme.card(root)
        panel.pack()
        self.assertEqual(style.lookup(panel.cget('style'), 'background'), '#FFFFFF')
        self.assertEqual(style.lookup('DB.Muted.TLabel', 'foreground'), '#5C6270')
        theme.apply_theme(root)  # Reapplying for an owned Toplevel must be safe.
        window = tk.Toplevel(root)
        theme.apply_theme(window)
        self.assertEqual(window.cget('background').lower(), '#f1f3f8')

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
        self.assertEqual(root.cget('background').lower(), '#f1f3f8')
        self.assertEqual(ttk.Style(root).theme_use(), 'clam')

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
                    self.assertEqual((root.winfo_width(), root.winfo_height()), (940, 760))
                    cards = [w for w in descendants(root) if isinstance(w, ttk.Frame)
                             and w.cget('style') == 'DB.Card.TFrame'
                             and isinstance(w.master.master, tk.Canvas)]
                    self.assertEqual(len(cards), 3)
                    for size in ('940x760', '800x600'):
                        root.geometry(size)
                        root.update()
                        canvases = [w for w in descendants(root) if isinstance(w, tk.Canvas)]
                        self.assertEqual(len(canvases), 1)
                        canvas = canvases[0]
                        self.assertLessEqual(canvas.winfo_width(), root.winfo_width())
                        for widget in descendants(canvas):
                            if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Label)):
                                self.assertGreaterEqual(widget.winfo_rootx(), canvas.winfo_rootx())
                                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                                     canvas.winfo_rootx() + canvas.winfo_width())
                                self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())
                        canvas.yview_moveto(0)
                        root.update()
                        if size == '800x600':
                            self.assertLess(canvas.yview()[1], 1.0)
                            canvas.event_generate('<MouseWheel>', delta=-120)
                            root.update()
                            self.assertGreater(canvas.yview()[0], 0.0)
                        canvas.yview_moveto(1)
                        root.update()
                        last = next(w for w in descendants(canvas) if isinstance(w, ttk.Button)
                                    and w.cget('text') == 'Настроить видео и звук')
                        self.assertLessEqual(last.winfo_rooty() + last.winfo_height(),
                                             canvas.winfo_rooty() + canvas.winfo_height())
                        canvas.yview_moveto(0)
                        last.event_generate('<FocusIn>')
                        root.update()
                        self.assertGreaterEqual(last.winfo_rooty(), canvas.winfo_rooty())
                        self.assertLessEqual(last.winfo_rooty() + last.winfo_height(),
                                             canvas.winfo_rooty() + canvas.winfo_height())
                    texts = [w.cget('text') for w in descendants(root) if isinstance(w, ttk.Label)]
                    self.assertIn('Подключение', texts)
                    self.assertIn('Экран телефона на ПК', texts)
                    self.assertIn('Инструменты', texts)
                finally:
                    root.destroy()
            with patch.object(sys, 'argv', ['launcher']), \
                 patch.object(launcher, 'data_directory', return_value=Path(isolated)), \
                 patch('runtime.create_update_signal', return_value=None), \
                 patch('android_setup.should_show_on_startup', return_value=False), \
                 patch('update_manager.start_startup_check'), \
                 patch.object(launcher, 'start_child', side_effect=AssertionError('no child startup')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('no network')), \
                 patch.object(socket.socket, 'bind', side_effect=AssertionError('no listener')), \
                 patch.object(tk.Tk, 'mainloop', inspect):
                self.assertEqual(launcher.main(), 0)


if __name__ == '__main__':
    unittest.main()
