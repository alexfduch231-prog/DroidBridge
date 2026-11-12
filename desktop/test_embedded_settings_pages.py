"""Embedded settings share one Tk owner and survive navigation during validation."""
from contextlib import nullcontext
from pathlib import Path
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from desktop import apps_panel, media_setup, upload_panel
from listener import media_tools


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class EmbeddedSettingsPagesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name) / 'data'
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)

    def test_builders_embed_controls_without_creating_or_managing_windows(self):
        builders = (
            (apps_panel, 'build_apps_page', ttk.Treeview),
            (upload_panel, 'build_uploads_page', ttk.Entry),
            (media_setup, 'build_media_page', ttk.Entry),
        )
        for module, name, control in builders:
            with self.subTest(page=name):
                self.assertTrue(hasattr(module, name), 'embedded page builder is required')
                page = getattr(module, name)(self.root, self.data)
                self.assertIs(page.master, self.root)
                self.assertEqual(page.winfo_manager(), '')
                page.pack(fill='both', expand=True)
                self.root.update()
                self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(self.root)))
                self.assertTrue(any(isinstance(w, control) for w in descendants(page)))
                close_labels = {'Close', 'Закрыть'}
                self.assertFalse(any(isinstance(w, ttk.Button) and w.cget('text') in close_labels
                                     for w in descendants(page)))
                page.dispose()
                page.dispose()
                self.assertFalse(page.winfo_exists())
        self.assertEqual(self.errors, [])

    def test_narrow_sidebar_pages_keep_whole_controls_visible_at_high_dpi(self):
        from desktop.theme import apply_theme
        self.root.deiconify()
        self.root.geometry('800x600')
        previous_scaling = self.root.tk.call('tk', 'scaling')
        self.addCleanup(lambda: self.root.tk.call('tk', 'scaling', previous_scaling))
        self.root.tk.call('tk', 'scaling', 3.0)
        apply_theme(self.root)
        sidebar = ttk.Frame(self.root, width=300)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        host = ttk.Frame(self.root)
        host.pack(side='left', fill='both', expand=True)
        for module, builder in ((apps_panel, 'build_apps_page'),
                                (upload_panel, 'build_uploads_page'),
                                (media_setup, 'build_media_page')):
            language = (patch.object(module.locale, 'getlocale', return_value=('ru_RU', 'UTF-8'))
                        if hasattr(module, 'locale') else nullcontext())
            with self.subTest(page=builder), language:
                page = getattr(module, builder)(host, self.data)
                page.pack(fill='both', expand=True)
                self.root.update()
                canvas = next(w for w in descendants(page) if isinstance(w, tk.Canvas))
                for control in descendants(page):
                    if not isinstance(control, (ttk.Button, ttk.Entry, ttk.Treeview)):
                        continue
                    control.event_generate('<FocusIn>')
                    self.root.update()
                    self.assertGreaterEqual(control.winfo_rootx(), canvas.winfo_rootx(), str(control))
                    self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                         canvas.winfo_rootx() + canvas.winfo_width(), str(control))
                page.dispose()
        self.assertEqual(self.errors, [])

    def test_legacy_windows_use_the_same_builders(self):
        cases = (
            (apps_panel, 'show_apps', 'build_apps_page'),
            (upload_panel, 'show_uploads', 'build_uploads_page'),
            (media_setup, 'show_media_setup', 'build_media_page'),
        )
        for module, wrapper, builder in cases:
            with self.subTest(wrapper=wrapper):
                self.assertTrue(hasattr(module, builder), 'wrapper must reuse embedded builder')
                with patch.object(module, builder, wraps=getattr(module, builder)) as build:
                    window = getattr(module, wrapper)(self.root, self.data)
                self.assertIsInstance(window, tk.Toplevel)
                self.assertEqual(build.call_count, 1)
                self.assertIs(build.call_args.args[0], window)
                self.assertEqual(build.call_args.args[1], self.data)
                window.destroy()

    def test_destroy_or_dispose_during_validation_cancels_tk_poll_not_worker_save(self):
        self.assertTrue(hasattr(media_setup, 'build_media_page'), 'embedded media builder is required')
        folder = self.data.parent / 'tools'
        folder.mkdir()
        for name in ('ffmpeg.exe', 'ffplay.exe'):
            (folder / name).touch()
        for action in ('destroy', 'dispose'):
            with self.subTest(action=action):
                media_tools.reset_media_directory(self.data)
                page = media_setup.build_media_page(self.root, self.data)
                page.pack(fill='both', expand=True)
                self.root.update()
                choose = next(w for w in descendants(page) if isinstance(w, ttk.Button)
                              and w.cget('text') == 'Выбрать папку…')
                entered, release = threading.Event(), threading.Event()
                workers = []
                start = media_setup.start_media_setup

                def track_worker(*args):
                    worker = start(*args)
                    workers.append(worker)
                    return worker

                def probe(*args, **kwargs):
                    entered.set()
                    release.wait(3)
                    return subprocess.CompletedProcess(args[0], 0)

                before = set(self.root.tk.call('after', 'info'))
                with patch('tkinter.filedialog.askdirectory', return_value=str(folder)), \
                     patch('tkinter.messagebox.askyesno', return_value=True), \
                     patch.object(media_setup, 'start_media_setup', side_effect=track_worker), \
                     patch.object(media_tools.subprocess, 'run', side_effect=probe):
                    choose.invoke()
                    try:
                        self.assertTrue(entered.wait(1))
                        polling = set(self.root.tk.call('after', 'info')) - before
                        self.assertTrue(polling, 'validation must be polled without blocking Tk')
                        getattr(page, action)()
                        self.assertFalse(polling & set(self.root.tk.call('after', 'info')))
                        self.assertTrue(workers[0].is_alive(), 'navigation must not kill validation')
                    finally:
                        release.set()
                        for worker in workers:
                            worker.join(3)
                self.assertFalse(workers[0].is_alive())
                self.root.update()
                self.assertEqual(media_tools.resolve_media_tools(self.data).source, 'configured')
                self.assertEqual(self.errors, [])

    def test_reopened_media_page_cannot_reset_or_replace_pending_validation(self):
        import time
        entered, release = threading.Event(), threading.Event()
        workers = []
        start = media_setup.start_media_setup

        def save(*args):
            entered.set()
            release.wait(3)
            return object()

        def track(*args):
            worker = start(*args)
            workers.append(worker)
            return worker

        with patch.object(media_setup, 'save_media_directory', side_effect=save), \
             patch.object(media_setup, 'start_media_setup', side_effect=track), \
             patch('tkinter.filedialog.askdirectory', return_value='chosen-tools'), \
             patch('tkinter.messagebox.askyesno', return_value=True), \
             patch.object(media_setup, 'reset_media_directory') as reset:
            first = media_setup.build_media_page(self.root, self.data)
            next(w for w in descendants(first) if isinstance(w, ttk.Button)
                 and w.cget('text') == 'Выбрать папку…').invoke()
            self.assertTrue(entered.wait(1))
            first.dispose()
            second = media_setup.build_media_page(self.root, self.data)
            second.pack(fill='both', expand=True)
            controls = [w for w in descendants(second) if isinstance(w, ttk.Button)
                        and w.cget('text') in ('Выбрать папку…', 'Автоматический поиск')]
            try:
                for button in controls:
                    self.assertIn('disabled', button.state())
                    button.invoke()
                reset.assert_not_called()
                self.assertEqual(len(workers), 1)
            finally:
                release.set()
                for worker in workers:
                    worker.join(3)
            deadline = time.monotonic() + 1
            while second.is_busy() and time.monotonic() < deadline:
                self.root.update()
            self.assertFalse(second.is_busy())
            self.assertTrue(all('disabled' not in button.state() for button in controls))
            next(button for button in controls if button.cget('text') == 'Автоматический поиск').invoke()
            reset.assert_called_once_with(self.data)
            self.assertEqual(len(workers), 1, 'finished validation cannot run or save again after reset')
            self.assertFalse(media_setup._media_busy(self.data))
            second.dispose()
        self.assertEqual(self.errors, [])

    def test_embedded_scroll_focus_and_wheel_are_scoped_and_bindings_are_released(self):
        from desktop.theme import scrollable_card
        self.root.deiconify()
        self.root.geometry('500x300')
        outside = ttk.Button(self.root, text='Outside page')
        outside.pack()
        baseline = {event: self.root.bind(event) for event in ('<FocusIn>', '<MouseWheel>')}
        for _ in range(3):
            page = ttk.Frame(self.root)
            page.pack(fill='both', expand=True)
            content = scrollable_card(page)
            buttons = []
            for number in range(20):
                button = ttk.Button(content, text=f'Item {number}')
                button.pack(pady=5)
                buttons.append(button)
            self.root.update()
            canvas = next(w for w in descendants(page) if isinstance(w, tk.Canvas))
            self.assertLess(canvas.yview()[1], 1.0)
            buttons[-1].event_generate('<FocusIn>')
            self.root.update()
            self.assertGreaterEqual(buttons[-1].winfo_rooty(), canvas.winfo_rooty())
            self.assertLessEqual(buttons[-1].winfo_rooty() + buttons[-1].winfo_height(),
                                 canvas.winfo_rooty() + canvas.winfo_height())
            canvas.yview_moveto(0)
            buttons[0].event_generate('<MouseWheel>', delta=-120)
            self.root.update()
            self.assertGreater(canvas.yview()[0], 0.0)
            canvas.yview_moveto(0)
            outside.event_generate('<MouseWheel>', delta=-120)
            outside.event_generate('<FocusIn>')
            self.root.update()
            self.assertEqual(canvas.yview()[0], 0.0)
            page.destroy()
            self.root.update()
            for event, original in baseline.items():
                self.assertEqual(self.root.bind(event), original)
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
