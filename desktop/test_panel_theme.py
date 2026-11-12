"""Offline panel presentation contracts; no owner settings or network are used."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'listener'))


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PanelThemeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name) / 'data'

    def assert_light_panel(self, window):
        self.assertEqual(window.cget('background').lower(), '#f1f3f8')
        buttons = [w for w in descendants(window) if isinstance(w, ttk.Button)]
        self.assertTrue(any(w.cget('style') == 'DB.Primary.TButton' for w in buttons))
        frames = [w for w in descendants(window) if isinstance(w, ttk.Frame)]
        self.assertTrue(any(w.cget('style') == 'DB.Card.TFrame' for w in frames))
        self.root.deiconify()
        self.root.update()
        window.update_idletasks()
        for widget in descendants(window):
            if isinstance(widget, (ttk.Label, ttk.Button, ttk.Checkbutton, ttk.Entry)):
                self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight(), str(widget))
                self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), str(widget))

    def test_local_settings_and_update_offer_use_android_light_presentation(self):
        from android_setup import show_android_setup
        from apps_panel import show_apps
        from upload_panel import show_uploads
        import media_setup
        from update_manager import UpdateController
        with patch.object(media_setup, 'resolve_media_tools', return_value=SimpleNamespace(ffmpeg=None, ffplay=None)):
            for show in (lambda: show_android_setup(self.root, self.data, lambda: None),
                         lambda: show_apps(self.root, self.data),
                         lambda: show_uploads(self.root, self.data),
                         lambda: media_setup.show_media_setup(self.root, self.data)):
                window = show()
                try:
                    self.assert_light_panel(window)
                finally:
                    window.destroy()
        controller = UpdateController(self.root, self.data, None)
        with patch('update_manager.check_manifest', side_effect=AssertionError('offline test')):
            controller._offer({'windows': {'version': '99.0.0'}})
        self.assert_light_panel(controller.window)
        self.assertFalse(self.data.exists())

    def test_install_qr_keeps_white_quiet_zone_and_background(self):
        from android_setup import show_android_setup
        window = show_android_setup(self.root, self.data, lambda: None)
        next(w for w in descendants(window) if isinstance(w, ttk.Button)
             and w.cget('text') == 'Установить на телефон').invoke()
        label = next(w for w in descendants(window) if isinstance(w, ttk.Label)
                     and getattr(w, 'image', None) is not None)
        style = ttk.Style(window)
        self.assertEqual(style.lookup(label.cget('style'), 'background').lower(), '#ffffff')
        photo = label.image._PhotoImage__photo
        self.assertEqual(photo.get(0, 0), (255, 255, 255))
        self.assertFalse(self.data.exists())

    def test_scaled_panels_keep_controls_reachable_by_scroll_and_focus(self):
        from android_setup import show_android_setup
        from apps_panel import show_apps
        from upload_panel import show_uploads
        from pairing_panel import show_pairing
        import media_setup
        previous_scaling = self.root.tk.call('tk', 'scaling')
        self.addCleanup(lambda: self.root.tk.call('tk', 'scaling', previous_scaling))
        self.root.tk.call('tk', 'scaling', 2.0)
        self.root.deiconify()
        with patch.object(media_setup, 'resolve_media_tools', return_value=SimpleNamespace(ffmpeg=None, ffplay=None)), patch('lan_discovery.windows_adapters', return_value=[]):
            for show in (lambda: show_android_setup(self.root, self.data, lambda: None),
                         lambda: show_apps(self.root, self.data),
                         lambda: show_uploads(self.root, self.data),
                         lambda: media_setup.show_media_setup(self.root, self.data),
                         lambda: show_pairing(self.root, self.data)):
                window = show()
                try:
                    install = next((w for w in descendants(window) if isinstance(w, ttk.Button)
                                    and w.cget('text') == 'Установить на телефон'), None)
                    if install:
                        install.invoke()
                    window.geometry('800x500')
                    self.root.update()
                    canvas = next(w for w in descendants(window) if isinstance(w, tk.Canvas))
                    self.assertLessEqual(window.winfo_height(), 500)
                    for widget in descendants(window):
                        if isinstance(widget, (ttk.Button, ttk.Checkbutton)):
                            self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())
                            widget.focus_force()
                            self.root.update()
                            self.assertGreaterEqual(widget.winfo_rooty(), canvas.winfo_rooty())
                            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                                 canvas.winfo_rooty() + canvas.winfo_height())
                    canvas.yview_moveto(1)
                    self.root.update()
                    self.assertAlmostEqual(canvas.yview()[1], 1.0)
                finally:
                    window.destroy()
        self.assertFalse(self.data.exists())

    def test_pairing_qr_background_is_white_and_warning_is_danger(self):
        from pairing_panel import show_pairing
        with patch('lan_discovery.windows_adapters', return_value=[]):
            window = show_pairing(self.root, self.data)
        self.assert_light_panel(window)
        labels = [w for w in descendants(window) if isinstance(w, ttk.Label)]
        qr = next(w for w in labels if str(w.cget('anchor')) == 'center' and not w.cget('text'))
        warning = next(w for w in labels if 'TLS' in str(w.cget('text')))
        style = ttk.Style(window)
        self.assertEqual(style.lookup(qr.cget('style'), 'background').lower(), '#ffffff')
        self.assertEqual(style.lookup(warning.cget('style'), 'foreground').lower(), '#cc2f23')
        self.assertFalse(self.data.exists())


if __name__ == '__main__':
    unittest.main()
