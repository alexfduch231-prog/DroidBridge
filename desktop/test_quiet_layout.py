"""Mapped Tk checks for the quiet shell and work-area-bounded default size."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch


class QuietLayoutTests(unittest.TestCase):
    def run_shell(self, inspect, workarea=(0, 0, 1920, 1080)):
        for folder in ('desktop', 'listener'):
            path = str(Path(__file__).resolve().parents[1] / folder)
            sys.path.insert(0, path)
            self.addCleanup(lambda path=path: sys.path.remove(path))
        launcher = importlib.import_module('desktop.launcher')
        errors = []
        def mainloop(root):
            root.report_callback_exception = lambda *args: errors.append(args)
            try:
                root.update()
                inspect(root)
            finally:
                root.destroy()
            self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ), patch.object(launcher, 'data_directory', return_value=Path(directory)), patch('update_manager.start_startup_check'), patch('desktop.mirror_handoff.GuiMirrorHandoff'), patch('desktop.window_chrome._Win32.monitor', return_value=(workarea, workarea)), patch.object(tk.Tk, 'winfo_screenwidth', return_value=workarea[2] - workarea[0]), patch.object(tk.Tk, 'winfo_screenheight', return_value=workarea[3] - workarea[1]), patch.object(tk.Tk, 'mainloop', mainloop):
            self.assertEqual(launcher.run_launcher(), 0)

    def test_default_window_leaves_space_for_normal_dpi_content(self):
        def inspect(root):
            self.assertGreaterEqual(root.winfo_width(), 1040)
            self.assertGreaterEqual(root.winfo_height(), 780)
            self.assertEqual(root.minsize(), (800, 600))
            self.assertEqual(root.resizable(), (1, 1))
        self.run_shell(inspect)

    def test_default_window_fits_smaller_work_area_with_margin(self):
        def inspect(root):
            self.assertGreaterEqual(root.winfo_width(), 800)
            self.assertGreaterEqual(root.winfo_height(), 600)
            self.assertLessEqual(root.winfo_width(), 952)
            self.assertLessEqual(root.winfo_height(), 692)
        self.run_shell(inspect, workarea=(0, 0, 1000, 740))

    def test_tiny_work_area_reduces_minimum_instead_of_hiding_window_edges(self):
        def inspect(root):
            self.assertLessEqual(root.winfo_width(), 712)
            self.assertLessEqual(root.winfo_height(), 512)
            self.assertEqual(root.minsize(), (712, 512))
        self.run_shell(inspect, workarea=(0, 0, 760, 560))

    def test_shell_and_header_do_not_draw_permanent_dividers(self):
        def inspect(root):
            workspace = root.navigation.master
            shell = workspace.master
            self.assertFalse(any(isinstance(w, ttk.Separator)
                                 for parent in (shell, workspace)
                                 for w in parent.winfo_children()))
            self.assertIsNotNone(root.window_chrome)
            self.assertTrue(root.protocol('WM_DELETE_WINDOW'))
            self.assertEqual(workspace.cget('style'), shell.cget('style'))
        self.run_shell(inspect)


if __name__ == '__main__':
    unittest.main()
