"""Media discovery, opt-in validation and non-blocking local setup."""
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    from listener import media_tools
    from desktop import media_setup
except ImportError:
    media_tools = media_setup = None


class MediaSetupTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(media_tools, 'shared media resolver must exist')
        self.assertIsNotNone(media_setup, 'local media setup must exist')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'data'

    def pair(self, name='FFmpeg с пробелами', nested=False):
        folder = self.root / name
        target = folder / 'bin' if nested else folder
        target.mkdir(parents=True)
        for tool in ('ffmpeg', 'ffplay'):
            (target / (tool + '.exe')).touch()
        return folder, target

    def test_no_settings_discovers_distribution_without_executing(self):
        folder, target = self.pair(nested=True)
        with patch.object(media_tools.subprocess, 'run') as run:
            tools = media_tools.resolve_media_tools(self.data, media_dir=folder)
        self.assertEqual(tools.ffmpeg, str(target / 'ffmpeg.exe'))
        self.assertEqual(tools.ffplay, str(target / 'ffplay.exe'))
        self.assertEqual(tools.source, 'distribution')
        run.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_no_settings_falls_back_to_path(self):
        with patch.object(media_tools.shutil, 'which', side_effect=lambda name: 'C:/tools/' + name + '.exe'):
            tools = media_tools.resolve_media_tools(self.data, media_dir=self.root / 'missing')
        self.assertEqual(tools.source, 'path')
        self.assertEqual(tools.ffplay, 'C:/tools/ffplay.exe')

    def test_validates_both_tools_with_timeout_and_no_shell_then_saves(self):
        folder, target = self.pair(nested=True)
        with patch.object(media_tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            tools = media_tools.save_media_directory(self.data, folder)
        self.assertEqual(run.call_count, 2)
        for call, name in zip(run.call_args_list, ('ffmpeg', 'ffplay')):
            self.assertEqual(call.args[0], [str(target / (name + '.exe')), '-version'])
            self.assertEqual(call.kwargs['timeout'], 5.0)
            self.assertIs(call.kwargs['shell'], False)
        config = json.loads((self.data / 'media_settings.json').read_text(encoding='utf-8'))
        self.assertEqual(config, {'version': 1, 'directory': str(target)})
        with patch.object(media_tools.shutil, 'which', return_value='other'):
            self.assertEqual(media_tools.resolve_media_tools(self.data).ffmpeg, tools.ffmpeg)
        self.assertEqual(list(self.data.iterdir()), [self.data / 'media_settings.json'])

    def test_invalid_config_never_silently_uses_path(self):
        self.data.mkdir()
        for text in ('{bad', '[]', '{}', '{"version":1,"directory":"relative"}',
                     json.dumps({'version': 1, 'directory': str(self.root / 'gone')})):
            with self.subTest(text=text):
                (self.data / 'media_settings.json').write_text(text, encoding='utf-8')
                with patch.object(media_tools.shutil, 'which', return_value='unexpected') as which:
                    with self.assertRaises(media_tools.MediaToolsError):
                        media_tools.resolve_media_tools(self.data)
                    which.assert_not_called()

    def test_oversized_and_recursive_config_are_reported_safely(self):
        self.data.mkdir()
        settings = self.data / 'media_settings.json'
        folder, _ = self.pair()
        valid = json.dumps({'version': 1, 'directory': str(folder)})
        for text in (valid + ' ' * 16385, '[' * 2000 + '0' + ']' * 2000):
            settings.write_text(text, encoding='utf-8')
            with self.assertRaises(media_tools.MediaToolsError):
                media_tools.resolve_media_tools(self.data)

    def test_missing_one_tool_is_rejected_before_execution(self):
        folder, target = self.pair()
        (target / 'ffplay.exe').unlink()
        with patch.object(media_tools.subprocess, 'run') as run:
            with self.assertRaises(media_tools.MediaToolsError):
                media_tools.save_media_directory(self.data, folder)
        run.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_failed_probe_preserves_previous_settings_and_hides_private_paths(self):
        folder, _ = self.pair()
        self.data.mkdir()
        config = self.data / 'media_settings.json'
        config.write_text('previous', encoding='utf-8')
        for error in (subprocess.TimeoutExpired('private-location', 5), OSError('private-location')):
            with patch.object(media_tools.subprocess, 'run', side_effect=error):
                with self.assertRaises(media_tools.MediaToolsError) as raised:
                    media_tools.save_media_directory(self.data, folder)
                self.assertNotIn('private-location', str(raised.exception))
            self.assertEqual(config.read_text(), 'previous')
        with patch.object(media_tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)):
            with self.assertRaises(media_tools.MediaToolsError):
                media_tools.save_media_directory(self.data, folder)
        self.assertEqual(config.read_text(), 'previous')

    def test_replace_failure_preserves_old_file_and_cleans_temporary_file(self):
        folder, _ = self.pair()
        self.data.mkdir()
        config = self.data / 'media_settings.json'
        config.write_text('old', encoding='utf-8')
        with patch.object(media_tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            with patch.object(media_tools.os, 'replace', side_effect=OSError('private path')):
                with self.assertRaises(media_tools.MediaToolsError):
                    media_tools.save_media_directory(self.data, folder)
        self.assertEqual(config.read_text(), 'old')
        self.assertEqual(list(self.data.iterdir()), [config])

    def test_reset_restores_default_discovery(self):
        self.data.mkdir()
        (self.data / 'media_settings.json').write_text('bad')
        media_tools.reset_media_directory(self.data)
        media_tools.reset_media_directory(self.data)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(media_tools.shutil, 'which', return_value=None):
                original_is_file = Path.is_file
                def no_standard_install(path):
                    if str(path).replace('\\', '/').lower().startswith('c:/ffmpeg/'):
                        return False
                    return original_is_file(path)
                with patch.object(Path, 'is_file', no_standard_install):
                    self.assertIsNone(media_tools.resolve_media_tools(self.data, media_dir=self.root / 'none').ffmpeg)

    def test_worker_returns_before_validation_finishes_and_reports_via_queue(self):
        started, release = threading.Event(), threading.Event()
        results = queue.Queue()
        owner = threading.get_ident()
        seen = []
        def save(*args):
            seen.append(threading.get_ident())
            started.set()
            release.wait(2)
            return 'saved'
        with patch.object(media_setup, 'save_media_directory', side_effect=save):
            worker = media_setup.start_media_setup(self.data, 'selected', results)
            try:
                self.assertTrue(started.wait(1))
                self.assertTrue(worker.is_alive())
                self.assertTrue(results.empty())
                self.assertNotEqual(seen, [owner])
            finally:
                release.set()
                worker.join(2)
        self.assertEqual(results.get_nowait(), (True, 'saved'))

    def test_worker_failure_is_generic(self):
        results = queue.Queue()
        with patch.object(media_setup, 'save_media_directory', side_effect=OSError('secret')):
            worker = media_setup.start_media_setup(self.data, 'folder', results)
            worker.join(2)
        success, message = results.get_nowait()
        self.assertFalse(success)
        self.assertNotIn('secret', message)

    def test_server_and_viewer_share_configured_snapshot(self):
        from desktop import runtime
        folder, target = self.pair()
        with patch.object(media_tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            media_tools.save_media_directory(self.data, folder)
        with patch.dict(os.environ, {'VZAIMOPULT_DATA_DIR': str(self.data)}):
            modules = [runtime.load_component(name) for name in ('server', 'viewer')]
        for module in modules:
            self.assertEqual(module.MEDIA_TOOLS.ffmpeg, str(target / 'ffmpeg.exe'))
            self.assertEqual(module.MEDIA_TOOLS.ffplay, str(target / 'ffplay.exe'))
        media_tools.reset_media_directory(self.data)
        for module in modules:
            self.assertEqual(module.MEDIA_TOOLS.ffplay, str(target / 'ffplay.exe'))

    def test_broken_explicit_folder_disables_both_processes_without_fallback(self):
        from desktop import runtime
        self.data.mkdir()
        (self.data / 'media_settings.json').write_text('{broken', encoding='utf-8')
        with patch.dict(os.environ, {'VZAIMOPULT_DATA_DIR': str(self.data)}):
            modules = [runtime.load_component(name) for name in ('server', 'viewer')]
        for module in modules:
            self.assertEqual(module.MEDIA_TOOLS.source, 'invalid')
            self.assertIsNone(module.MEDIA_TOOLS.ffmpeg)
            self.assertIsNone(module.MEDIA_TOOLS.ffplay)

    def test_launcher_media_button_opens_local_window(self):
        import sys
        import tkinter as tk
        from tkinter import ttk
        path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, path)
        self.addCleanup(lambda: sys.path.remove(path))
        from desktop import launcher
        seen = []
        def inspect(root):
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            try:
                button = next(w for w in descendants(root) if isinstance(w, ttk.Button)
                              and w.cget('text') == 'Настроить видео и звук')
                button.invoke()
                root.update_idletasks()
                windows = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
                self.assertEqual(len(windows), 1)
                seen.append(windows[0].title())
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data):
            with patch.object(tk.Tk, 'mainloop', inspect), patch('update_manager.start_startup_check'):
                self.assertEqual(launcher.main(), 0)
        self.assertEqual(seen, ['Настроить видео и звук'])

    def test_runtime_does_not_modify_path(self):
        from desktop import runtime
        from types import SimpleNamespace
        import sys
        module = SimpleNamespace(main=lambda: 0)
        with patch.object(runtime, 'data_directory', return_value=self.data):
            with patch.object(runtime, 'load_component', return_value=module):
                with patch.dict(os.environ, {'PATH': 'unchanged'}), patch.object(sys, 'argv', ['launcher']):
                    runtime.run_component('viewer', [])
                    self.assertEqual(os.environ['PATH'], 'unchanged')

    def test_real_ui_explicit_consent_cancel_and_nonblocking_worker(self):
        import time
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        window = media_setup.show_media_setup(root, self.data)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons = {w.cget('text'): w for w in descendants(window) if isinstance(w, ttk.Button)}
        choose = buttons['Выбрать папку…']
        with patch('tkinter.filedialog.askdirectory', return_value=''):
            with patch.object(media_setup, 'start_media_setup') as start:
                choose.invoke()
                start.assert_not_called()
        with patch('tkinter.filedialog.askdirectory', return_value=str(self.root)):
            with patch('tkinter.messagebox.askyesno', return_value=False):
                with patch.object(media_setup, 'start_media_setup') as start:
                    choose.invoke()
                    start.assert_not_called()
        entered, release = threading.Event(), threading.Event()
        def save(*args):
            entered.set()
            release.wait(3)
            return media_tools.MediaTools(None, None, 'path')
        with patch('tkinter.filedialog.askdirectory', return_value=str(self.root)):
            with patch('tkinter.messagebox.askyesno', return_value=True):
                with patch.object(media_setup, 'save_media_directory', side_effect=save):
                    choose.invoke()
                    try:
                        self.assertTrue(entered.wait(1))
                        self.assertEqual(str(choose.cget('state')), 'disabled')
                        root.update()
                        self.assertTrue(window.winfo_exists())
                    finally:
                        release.set()
                    deadline = time.monotonic() + 2
                    while str(choose.cget('state')) == 'disabled' and time.monotonic() < deadline:
                        root.update()
                    self.assertEqual(str(choose.cget('state')), 'normal')
        texts = [w.cget('text') for w in descendants(window) if isinstance(w, ttk.Label)]
        self.assertTrue(any('исполняемые программы' in text for text in texts))
        root.deiconify()
        root.update()
        canvas = next(w for w in descendants(window) if isinstance(w, tk.Canvas))
        self.assertLessEqual(canvas.winfo_rooty() + canvas.winfo_height(),
                             window.winfo_rooty() + window.winfo_height())
        for button in buttons.values():
            button.focus_force()
            root.update()
            self.assertGreaterEqual(button.winfo_rooty(), canvas.winfo_rooty())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 canvas.winfo_rooty() + canvas.winfo_height())


if __name__ == '__main__':
    unittest.main()
