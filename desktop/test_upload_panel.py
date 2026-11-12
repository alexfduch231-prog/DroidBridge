"""Local settings model and real Tk controls, without services or network."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop import upload_panel
from listener import upload_settings


class UploadPanelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'data'
        self.default = self.root / 'Downloads'
        patcher = patch.object(upload_settings, 'downloads_folder', return_value=self.default)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.model = upload_panel.LocalUploadsModel(self.data)

    def test_selection_and_reset_update_persisted_destination(self):
        selected = self.root / 'Приём файлов'
        selected.mkdir()
        self.model.select_from_picker(str(selected))
        self.assertEqual(self.model.directory, selected)
        self.assertEqual(upload_settings.upload_directory(self.data), selected)
        self.model.reset()
        self.assertEqual(self.model.directory, self.default)
        self.assertFalse((self.data / 'upload_settings.json').exists())

    def test_cancel_does_not_create_settings(self):
        self.model.select_from_picker('')
        self.assertFalse((self.data / 'upload_settings.json').exists())

    def test_invalid_selection_keeps_previous_directory(self):
        selected = self.root / 'existing'
        selected.mkdir()
        self.model.select_from_picker(selected)
        with self.assertRaises(upload_settings.UploadSettingsError):
            self.model.select_from_picker(self.root / 'missing')
        self.assertEqual(self.model.directory, selected)

    def test_remote_mutations_rejected(self):
        with self.assertRaises(PermissionError):
            self.model.select_from_picker(self.root, source='remote')
        with self.assertRaises(PermissionError):
            self.model.reset(source='remote')
        self.assertFalse(self.data.exists())

    def test_corrupt_settings_can_be_recovered_by_reset(self):
        self.data.mkdir()
        (self.data / 'upload_settings.json').write_text('{broken', encoding='utf-8')
        with self.assertRaises(upload_settings.UploadSettingsError):
            _ = self.model.directory
        self.model.reset()
        self.assertEqual(self.model.directory, self.default)

    def test_launcher_embeds_upload_page_and_controls_fit(self):
        import sys
        import tkinter as tk
        from tkinter import ttk
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        self.addCleanup(lambda: sys.path.remove(str(Path(__file__).resolve().parent)))
        from desktop import launcher
        seen = []
        def inspect(root):
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            try:
                root.navigation.show_page('uploads')
                root.update_idletasks()
                page = root.navigation.pages['uploads']
                buttons = [w for w in descendants(page) if isinstance(w, ttk.Button)]
                self.assertTrue(buttons)
                windows = [w for w in descendants(root) if isinstance(w, tk.Toplevel)]
                self.assertEqual(windows, [])
                self.assertEqual(root.navigation.current_key, 'uploads')
                seen.append(root.navigation.current_key)
                canvas = next(w for w in descendants(page) if isinstance(w, tk.Canvas))
                for button in buttons:
                    button.focus_force()
                    root.update()
                    self.assertGreaterEqual(button.winfo_rooty(), canvas.winfo_rooty())
                    bottom = button.winfo_rooty() + button.winfo_height()
                    self.assertLessEqual(bottom, canvas.winfo_rooty() + canvas.winfo_height())
            finally:
                root.destroy()
        with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=self.data):
            with patch.object(tk.Tk, 'mainloop', inspect), patch('update_manager.start_startup_check'):
                self.assertEqual(launcher.main(), 0)
        self.assertEqual(len(seen), 1)

    def test_real_tk_picker_reset_and_sanitized_errors(self):
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        folder = self.root / 'selected'
        folder.mkdir()
        with patch.object(upload_panel.locale, 'getlocale', return_value=('en_US', 'UTF-8')):
            window = upload_panel.show_uploads(root, self.data)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons = {w.cget('text'): w for w in descendants(window) if isinstance(w, ttk.Button)}
        with patch('tkinter.filedialog.askdirectory', return_value=str(folder)) as picker:
            buttons['Choose folder…'].invoke()
        self.assertTrue(picker.call_args.kwargs['mustexist'])
        self.assertEqual(upload_settings.upload_directory(self.data), folder)
        labels = [w.cget('textvariable') for w in descendants(window) if isinstance(w, ttk.Entry)]
        self.assertTrue(labels)
        self.assertEqual(window.getvar(labels[0]), str(folder))
        with patch('tkinter.filedialog.askdirectory', return_value=str(self.root / 'private-missing')):
            with patch('tkinter.messagebox.showerror') as error:
                buttons['Choose folder…'].invoke()
        self.assertTrue(error.called)
        self.assertNotIn('private-missing', str(error.call_args))
        buttons['Reset to Downloads'].invoke()
        self.assertEqual(upload_settings.upload_directory(self.data), self.default)
        window.update_idletasks()
        for button in buttons.values():
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), button.master.winfo_height())


if __name__ == '__main__':
    unittest.main()
