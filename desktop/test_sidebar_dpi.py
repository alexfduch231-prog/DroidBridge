"""Mapped native Tk regression tests for sidebar sizing and keyboard access."""
import importlib
import os
from pathlib import Path
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


class SidebarDpiTests(unittest.TestCase):
    def run_shell(self, scaling, inspect):
        for folder in ('desktop', 'listener'):
            path = str(Path(__file__).resolve().parents[1] / folder)
            sys.path.insert(0, path)
            self.addCleanup(lambda path=path: sys.path.remove(path))
        launcher = importlib.import_module('desktop.launcher')
        original_init = tk.Tk.__init__
        def initialize(root, *args, **kwargs):
            original_init(root, *args, **kwargs)
            root._test_previous_scaling = root.tk.call('tk', 'scaling')
            root.tk.call('tk', 'scaling', scaling)
        def mainloop(root):
            try:
                root.geometry('800x600')
                root.update()
                inspect(root)
            finally:
                root.tk.call('tk', 'scaling', root._test_previous_scaling)
                root.destroy()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ), patch.object(launcher, 'data_directory', return_value=Path(directory)), patch('update_manager.start_startup_check'), patch('desktop.mirror_handoff.GuiMirrorHandoff'), patch.object(tk.Tk, '__init__', initialize), patch.object(tk.Tk, 'mainloop', mainloop):
            self.assertEqual(launcher.run_launcher(), 0)

    def sidebar_buttons(self, root):
        return [w for w in descendants(root) if isinstance(w, ttk.Button) and
                (str(w.cget('style')).startswith('DB.Nav.') or
                 ''.join(str(w.cget('text')).split()) == 'Проверитьобновления')]

    def test_native_requested_width_fits_at_minimum_window_for_every_dpi(self):
        for scaling in (4 / 3, 2, 3, 4):
            with self.subTest(scaling=scaling):
                def inspect(root):
                    buttons = self.sidebar_buttons(root)
                    self.assertEqual(len(buttons), 7)
                    for button in buttons:
                        self.assertTrue(button.winfo_ismapped())
                        self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width(),
                                             (button.cget('text'), scaling, button.winfo_reqwidth(), button.winfo_width()))
                        style = ttk.Style(button)
                        padding = button.tk.splitlist(style.lookup(button.cget('style'), 'padding'))
                        horizontal = int(padding[0]) * 2
                        if len(padding) >= 3:
                            horizontal = int(padding[0]) + int(padding[2])
                        parcel = button.winfo_width() - horizontal - (16 if button.cget('image') else 0)
                        for line in str(button.cget('text')).splitlines():
                            measured = int(button.tk.call('font', 'measure', style.lookup(button.cget('style'), 'font'), line))
                            self.assertLessEqual(measured, parcel, (line, measured, parcel))
                self.run_shell(scaling, inspect)

    def test_existing_pixel_fonts_reflow_after_tk_scaling_changes(self):
        def inspect(root):
            root.tk.call('tk', 'scaling', 1.33)
            root.geometry('940x760')
            root.update()
            for button in self.sidebar_buttons(root):
                button.event_generate('<FocusIn>')
                root.update()
                self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width(), button.cget('text'))
        self.run_shell(2, inspect)

    def test_every_sidebar_action_can_be_revealed_by_keyboard_focus_at_300_percent(self):
        def inspect(root):
            buttons = self.sidebar_buttons(root)
            self.assertEqual(len(buttons), 7)
            for button in buttons:
                button.focus_force()
                root.update()
                self.assertIs(root.focus_get(), button)
                self.assertGreaterEqual(button.winfo_rooty(), root.winfo_rooty())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     root.winfo_rooty() + root.winfo_height())
                # Native Tab traversal must retain every action in its focus chain.
                self.assertTrue(str(button.tk.call('tk_focusNext', button)))
        self.run_shell(4, inspect)


if __name__ == '__main__':
    unittest.main()
