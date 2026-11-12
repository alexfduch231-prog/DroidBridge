"""GUI-only, read-only deferred WOL diagnostics and embedded navigation."""
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


class LauncherWolTests(unittest.TestCase):
    def run_shell(self, inspect, start):
        path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, path)
        self.addCleanup(lambda: sys.path.remove(path))
        launcher = importlib.import_module('desktop.launcher')
        pending = {}
        serial = [0]
        def after(root, delay, callback=None, *args):
            serial[0] += 1
            key = 'test-after-%s' % serial[0]
            pending[key] = (delay, callback, args)
            return key
        def cancel(root, key):
            pending.pop(key, None)
        def run_delay(delay):
            key = next(key for key, item in pending.items() if item[0] == delay)
            _, callback, args = pending.pop(key)
            callback(*args)
        errors = []
        def mainloop(root):
            root.report_callback_exception = lambda *args: errors.append(args)
            try:
                inspect(root, pending, run_delay)
            finally:
                try:
                    root.destroy()
                except tk.TclError:
                    pass
            self.assertFalse(pending, 'root cleanup must cancel every owned timer')
            self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ), patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=Path(directory)), patch('runtime.create_update_signal', return_value=None), patch('update_manager.start_startup_check'), patch('desktop.mirror_handoff.GuiMirrorHandoff'), patch('wol_setup.start_diagnostics', side_effect=start) as worker, patch('wol_setup.configure_windows', side_effect=AssertionError('no automatic changes')), patch.object(tk.Tk, 'after', after), patch.object(tk.Tk, 'after_cancel', cancel), patch.object(tk.Tk, 'mainloop', mainloop):
            self.assertEqual(launcher.main(), 0)
        return worker

    def test_deferred_once_progress_result_and_embedded_page(self):
        from desktop.wol_setup import WolReport
        queues = []
        def start(results):
            queues.append(results)
            self.assertGreater(results.maxsize, 0)
            results.put(('progress', 2))
        def inspect(root, pending, run_delay):
            root.update()
            self.assertEqual(queues, [])
            run_delay(1500)
            self.assertEqual(len(queues), 1)
            run_delay(100)
            self.assertIn('2/3', root.wol_status.get())
            queues[0].put(('done', WolReport('Ethernet', '', 'enabled')))
            run_delay(100)
            self.assertIn('не проверено', root.wol_status.get())
            self.assertNotIn(100, [value[0] for value in pending.values()])
            root.geometry('800x600')
            for scaling in (2.0, 3.0):
                root.tk.call('tk', 'scaling', scaling)
                root.update()
                for widget in descendants(root):
                    if isinstance(widget, ttk.Button) and widget.cget('text') in ('Включение ПК', 'Настройки'):
                        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), root.winfo_rooty() + root.winfo_height())
            root.show_section('screen')
            root.show_section('connection')
            self.assertEqual(len(queues), 1)
            with patch('wol_setup.build_wol_page', side_effect=lambda parent, data: ttk.Frame(parent)) as build:
                next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == 'Включение ПК').invoke()
                self.assertEqual(root.navigation.current_key, 'wol')
                build.assert_called_once()
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
        self.run_shell(inspect, start).assert_called_once()

    def test_closed_root_ignores_late_worker_result(self):
        queues = []
        def inspect(root, pending, run_delay):
            run_delay(1500)
            self.assertEqual(len(queues), 1)
            root.destroy()
            self.assertFalse(pending)
            queues[0].put(('error', 'late result'))
        self.run_shell(inspect, lambda results: queues.append(results)).assert_called_once()

    def test_close_before_deferred_start_never_probes(self):
        self.run_shell(lambda root, pending, run_delay: root.destroy(), lambda results: None).assert_not_called()
