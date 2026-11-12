"""Single-window navigation and launcher opt-in/lifecycle regression tests."""
import importlib
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


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)

    def test_switch_disposes_previous_page_and_never_leaves_hidden_pairing(self):
        from desktop.navigation import PageHost
        disposed = []
        def builder(name):
            def build(parent):
                frame = ttk.Frame(parent)
                ttk.Label(frame, text=name).pack()
                def dispose():
                    disposed.append(name)
                    frame.destroy()
                frame.dispose = dispose
                return frame
            return build
        host = PageHost(self.root, {'connection': builder('pairing'), 'apps': builder('apps')})
        host.pack(fill='both', expand=True)
        first = host.show_page('connection')
        self.assertIs(host.show_page('connection'), first)
        second = host.show_page('apps')
        self.assertEqual(disposed, ['pairing'])
        self.assertFalse(first.winfo_exists())
        self.assertEqual(host.current_key, 'apps')
        self.assertTrue(second.winfo_exists())
        host.dispose()
        host.dispose()
        self.assertEqual(disposed, ['pairing', 'apps'])

    def test_cleanup_only_pages_are_destroyed_and_root_destroy_disposes_once(self):
        from desktop.navigation import PageHost
        disposed = []
        def build(parent):
            page = ttk.Frame(parent)
            page.dispose = lambda: disposed.append('cleanup')
            return page
        host = PageHost(self.root, {'connection': build, 'apps': build})
        first = host.show_page('connection')
        host.show_page('apps')
        self.assertFalse(first.winfo_exists())
        host.destroy()
        self.assertEqual(disposed, ['cleanup', 'cleanup'])

    def test_failed_builder_destroys_partial_page_and_its_resources(self):
        from desktop.navigation import PageHost
        disposed = []
        def failing(parent):
            page = ttk.Frame(parent)
            page.dispose = lambda: disposed.append('closed')
            raise OSError('cannot load page')
        host = PageHost(self.root, {'broken': failing})
        with self.assertRaisesRegex(OSError, 'cannot load page'):
            host.show_page('broken')
        self.assertEqual(host.winfo_children(), [])
        self.assertEqual(disposed, ['closed'])

    def test_dispose_failure_still_destroys_previous_page(self):
        from desktop.navigation import PageHost
        def build(parent):
            page = ttk.Frame(parent)
            def dispose():
                raise OSError('cleanup failed')
            page.dispose = dispose
            return page
        host = PageHost(self.root, {'connection': build})
        page = host.show_page('connection')
        with self.assertRaisesRegex(OSError, 'cleanup failed'):
            host.dispose()
        self.assertFalse(page.winfo_exists())

    def test_unknown_page_keeps_current_content(self):
        from desktop.navigation import PageHost
        host = PageHost(self.root, {'connection': lambda parent: ttk.Frame(parent)})
        host.show_page('connection')
        with self.assertRaises(KeyError):
            host.show_page('missing')
        self.assertEqual(host.current_key, 'connection')
        self.assertTrue(host.pages['connection'].winfo_exists())


class LauncherNavigationTests(unittest.TestCase):
    def setUp(self):
        import os
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)

    def test_saved_startup_optout_keeps_installation_explicit(self):
        path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, path)
        self.addCleanup(lambda: sys.path.remove(path))
        launcher = importlib.import_module('desktop.launcher')
        import android_setup
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            android_setup.save_dont_show(data, True)
            original = android_setup.build_android_setup_page
            with patch.object(android_setup, 'build_android_setup_page', wraps=original) as setup:
                def inspect(root):
                    try:
                        root.update()
                        setup.assert_not_called()
                        self.assertEqual(root.navigation.current_key, 'connection')
                        next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == 'Установить приложение Android').invoke()
                        root.update()
                        setup.assert_called_once()
                        self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
                        root.show_section('screen')
                        root.show_section('connection')
                        root.update()
                        self.assertEqual(setup.call_count, 1)
                        self.assertFalse(android_setup.should_show_on_startup(data))
                    finally:
                        root.destroy()
                with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=data), patch('runtime.create_update_signal', return_value=None), patch('update_manager.start_startup_check'), patch.object(tk.Tk, 'mainloop', inspect):
                    self.assertEqual(launcher.main(), 0)

    def test_startup_sections_viewer_token_guard_and_shutdown_cleanup(self):
        path = str(Path(__file__).resolve().parent)
        sys.path.insert(0, path)
        self.addCleanup(lambda: sys.path.remove(path))
        launcher = importlib.import_module('desktop.launcher')
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            starts = []
            self.addCleanup(patch.stopall)
            mirror = patch('desktop.mirror_handoff.GuiMirrorHandoff').start().return_value
            mirror.consume.return_value = None
            mirror.heartbeat.side_effect = OSError('startup handoff unavailable')
            class Child:
                stopped = False
                def poll(self):
                    return 0 if self.stopped else None
                def terminate(self):
                    self.stopped = True
            child = Child()
            def start(*args):
                starts.append(args)
                return child
            def inspect(root):
                try:
                    root.update()
                    self.assertEqual(starts, [])
                    self.assertEqual(root.navigation.current_key, 'connection')
                    self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
                    for scaling in (1.33, 2.0):
                        root.tk.call('tk', 'scaling', scaling)
                        root.geometry('800x600')
                        root.update()
                        for title in ('Подключение', 'Экран телефона', 'Программы', 'Приём файлов', 'Настройки'):
                            button = next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == title)
                            self.assertGreaterEqual(button.winfo_rooty(), root.winfo_rooty())
                            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), root.winfo_rooty() + root.winfo_height())
                    root.navigation.show_page('screen')
                    root.update()
                    entry = next(w for w in descendants(root) if isinstance(w, ttk.Entry))
                    entry.insert(0, '192.168.1.20')
                    button = next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == 'Открыть экран телефона')
                    button.invoke()
                    self.assertEqual(starts, [])
                    (data / 'token.txt').write_text('test-token')
                    from types import SimpleNamespace
                    disposed = []
                    automatic = []
                    endpoints = []
                    viewers = []
                    def build_viewer(parent, address, port, token, audio=True, *, auto_control=False):
                        automatic.append(auto_control)
                        self.assertEqual(token, 'test-token')
                        endpoints.append((address, port))
                        page = ttk.Frame(parent)
                        import threading
                        page.viewer = SimpleNamespace(stop=threading.Event())
                        viewers.append(page)
                        ttk.Label(page, text='Embedded viewer active').pack()
                        def dispose():
                            disposed.append(True)
                            page.destroy()
                        page.dispose = dispose
                        return page
                    component = SimpleNamespace(read_token=lambda path: Path(path).read_text(), build_viewer_page=build_viewer)
                    def load(component_name):
                        import os
                        self.assertEqual(os.environ.get('VZAIMOPULT_DATA_DIR'), str(data))
                        self.assertEqual(component_name, 'viewer')
                        return component
                    # A validated server handoff opens the same embedded viewer.
                    mirror.heartbeat.side_effect = None
                    mirror.consume.return_value = SimpleNamespace(host='192.168.1.20', port=8768)
                    with patch('runtime.load_component', side_effect=load):
                        root.poll_mirror_requests()
                    self.assertEqual(automatic, [True], 'phone handoff must enable one-shot control intent')
                    with patch('runtime.load_component', side_effect=load):
                        # A lost HTTP response can cause a duplicate before hello.
                        root.poll_mirror_requests()
                        self.assertEqual(endpoints, [('192.168.1.20', 8768)])
                        self.assertEqual(disposed, [])
                        viewers[0].viewer.authenticated = True
                        root.poll_mirror_requests()
                        self.assertEqual(disposed, [], 'healthy viewer must survive duplicate')
                        mirror.consume.return_value = SimpleNamespace(host='192.168.1.21', port=8769)
                        root.poll_mirror_requests()
                        self.assertEqual(endpoints[-1], ('192.168.1.21', 8769))
                        self.assertEqual(disposed, [True])
                        viewers[-1].viewer.stop.set()
                        root.poll_mirror_requests()
                        self.assertEqual(len(endpoints), 3, 'stopped viewer may be replaced')
                        self.assertEqual(disposed, [True, True])
                    mirror.consume.return_value = None
                    # File-system failures must not kill polling or strand callbacks.
                    for method in (mirror.heartbeat, mirror.consume):
                        method.side_effect = OSError('temporarily unavailable')
                        root.poll_mirror_requests()
                        method.side_effect = None
                    mirror.consume.return_value = SimpleNamespace(host='bad host', port='bad port')
                    root.poll_mirror_requests()
                    mirror.consume.return_value = None
                    root.poll_mirror_requests()
                    root.update()
                    self.assertEqual(starts, [], 'viewer must be embedded, not another process')
                    self.assertTrue(any(isinstance(w, ttk.Label) and w.cget('text') == 'Embedded viewer active' for w in descendants(root)))
                    root.navigation.show_page('connection')
                    root.update()
                    self.assertEqual(disposed, [True, True, True])
                    next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == 'Запустить сервер').invoke()
                    self.assertEqual(starts, [('server',)])
                    self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(root)))
                finally:
                    root.destroy()
            with patch.object(sys, 'argv', ['launcher']), patch.object(launcher, 'data_directory', return_value=data), patch('runtime.create_update_signal', return_value=None), patch('update_manager.start_startup_check'), patch.object(launcher, 'start_child', side_effect=start), patch.object(launcher.messagebox, 'showerror'), patch.object(tk.Tk, 'mainloop', inspect):
                self.assertEqual(launcher.main(), 0)
            self.assertTrue(child.stopped, 'root destruction must stop owned child processes')
            mirror.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
