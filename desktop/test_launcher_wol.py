"""Startup never probes WoL; explicit new pairing owns a disposable gate."""
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
    def run_shell(self, inspect):
        for folder in ('desktop', 'listener'):
            path = str(Path(__file__).resolve().parents[1] / folder)
            sys.path.insert(0, path)
            self.addCleanup(lambda path=path: sys.path.remove(path))
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
        errors = []
        def mainloop(root):
            root.report_callback_exception = lambda *args: errors.append(args)
            try:
                inspect(root, pending, Path(directory))
            finally:
                try:
                    root.destroy()
                except tk.TclError:
                    pass
            self.assertFalse(pending, 'root cleanup must cancel every owned timer')
            self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ), patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=Path(directory)), patch('runtime.create_update_signal', return_value=None), patch('update_manager.start_startup_check'), patch('desktop.mirror_handoff.GuiMirrorHandoff'), patch('wol_setup.start_diagnostics', side_effect=AssertionError('no startup probe')), patch('desktop.wol_setup.start_diagnostics', side_effect=AssertionError('no startup probe')), patch('wol_setup.configure_windows', side_effect=AssertionError('no automatic changes')), patch.object(tk.Tk, 'after', after), patch.object(tk.Tk, 'after_cancel', cancel), patch.object(tk.Tk, 'mainloop', mainloop):
            self.assertEqual(launcher.main(), 0)

    def test_no_startup_probe_and_first_pairing_opens_embedded_gate(self):
        def inspect(root, pending, data):
            root.update()
            self.assertNotIn(1500, [item[0] for item in pending.values()])
            with patch('desktop.wol_onboarding.build_onboarding_page', side_effect=lambda parent, data, on_completed: ttk.Frame(parent)) as gate, patch('pairing_panel.build_pairing_page', side_effect=AssertionError('pairing cannot bypass gate')):
                root.connection_pairing()
                self.assertEqual(root.navigation.current_key, 'connection')
                gate.assert_called_once()
                root.show_section('screen')
                root.show_section('connection')
                root.connection_pairing()
                self.assertEqual(gate.call_count, 2)
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
        self.run_shell(inspect)

    def test_existing_token_preserved_but_does_not_bypass_first_new_pairing(self):
        def inspect(root, pending, data):
            token = data / 'token.txt'
            token.write_text('existing-connection-key', encoding='utf-8')
            with patch('desktop.wol_onboarding.build_onboarding_page', side_effect=lambda parent, data, on_completed: ttk.Frame(parent)), patch('pairing_panel.build_pairing_page', side_effect=AssertionError('existing token is not completion')):
                root.connection_pairing()
                self.assertEqual(token.read_text('utf-8'), 'existing-connection-key')
        self.run_shell(inspect)

    def test_stale_gate_callback_cannot_open_pairing_after_navigation(self):
        import json
        def inspect(root, pending, data):
            callbacks = []
            def gate(parent, data_dir, on_completed):
                callbacks.append(on_completed)
                return ttk.Frame(parent)
            with patch('desktop.wol_onboarding.build_onboarding_page', side_effect=gate), patch('pairing_panel.build_pairing_page', side_effect=AssertionError('stale gate cannot open QR')):
                root.connection_pairing()
                (data / 'wol_onboarding.json').write_text(json.dumps({
                    'schema': 1, 'adapter_guid': '00000000-0000-0000-0000-000000000001',
                    'bios_manual_ack': True, 'network_compatible': True, 'completed': True}), encoding='utf-8')
                root.show_section('screen')
                callbacks[0]()
                self.assertEqual(root.navigation.current_key, 'screen')
        self.run_shell(inspect)

    def test_root_close_without_explicit_pairing_never_probes(self):
        self.run_shell(lambda root, pending, data: root.destroy())
