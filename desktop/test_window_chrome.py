"""Window chrome contracts; no existing app window or owner settings touched."""
import ctypes
import tkinter as tk
import unittest
from unittest.mock import patch

from desktop import window_chrome as chrome


class HitTestTests(unittest.TestCase):
    def test_all_eight_resize_regions_and_negative_monitor_origin(self):
        rect = (-1200, -300, -400, 300)
        points = [((-1200, -300), 13), ((-800, -300), 12), ((-401, -300), 14),
                  ((-1200, 0), 10), ((-401, 0), 11), ((-1200, 299), 16),
                  ((-800, 299), 15), ((-401, 299), 17)]
        for point, expected in points:
            self.assertEqual(chrome.hit_test(point, rect, 8, 40), expected)

    def test_caption_excludes_buttons_and_maximized_window_has_no_resize(self):
        rect = (0, 0, 800, 600)
        self.assertEqual(chrome.hit_test((30, 20), rect, 8, 40), 2)
        self.assertEqual(chrome.hit_test((760, 20), rect, 8, 40, interactive=True), 1)
        self.assertEqual(chrome.hit_test((0, 20), rect, 8, 40, maximized=True), 2)
        self.assertEqual(chrome.hit_test((30, 100), rect, 8, 40), 1)

    def test_signed_packed_coordinates(self):
        self.assertEqual(chrome.point_from_lparam((0xFF38 << 16) | 0xFB50), (-1200, -200))

    def test_work_area_is_relative_to_monitor_not_primary_origin(self):
        info = chrome.MINMAXINFO()
        chrome.apply_work_area(info, (-1920, -200, 0, 880), (-1920, -160, 0, 880), (800, 600))
        self.assertEqual((info.ptMaxPosition.x, info.ptMaxPosition.y), (0, 40))
        self.assertEqual((info.ptMaxSize.x, info.ptMaxSize.y), (1920, 1040))
        self.assertEqual((info.ptMinTrackSize.x, info.ptMinTrackSize.y), (800, 600))


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.maximized = False
    def install(self, hwnd, callback):
        self.calls.append(('install', hwnd)); self.callback = callback
    def remove(self, hwnd, callback): self.calls.append(('remove', hwnd))
    def frame_changed(self, hwnd): self.calls.append(('frame', hwnd))
    def extend(self, hwnd, enabled): self.calls.append(('extend', enabled))
    def default(self, hwnd, msg, wp, lp): self.calls.append(('default', msg)); return 73
    def rect(self, hwnd): return (0, 0, 800, 600)
    def dpi(self, hwnd): return 144
    def is_zoomed(self, hwnd): return self.maximized
    def monitor(self, hwnd): return ((-1920, 0, 0, 1080), (-1920, 0, 0, 1040))
    def handle(self, root): return 123
    def drag(self, hwnd, region=2): self.calls.append(('drag', region))
    def show(self, hwnd, command): self.calls.append(('show', command))
    def system_menu(self, hwnd): self.calls.append(('menu', hwnd))


class HookTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.closed = []
        self.hook = chrome.NativeHook(self.backend, 123, lambda: self.closed.append(True),
                                     lambda: (40, False), lambda: (800, 600))
        self.hook.install()
        self.addCleanup(self.hook.dispose)

    def test_close_routes_to_owner_and_other_messages_keep_chain(self):
        self.assertEqual(self.hook.dispatch(123, chrome.WM_CLOSE, 0, 0), 0)
        self.assertEqual(self.closed, [True])
        self.assertEqual(self.hook.dispatch(123, 999, 0, 0), 73)

    def test_nonclient_calc_retains_native_side_and_bottom_frame(self):
        rect = chrome.RECT(100, 200, 900, 800)
        def default(hwnd, msg, wp, lp):
            value = chrome.RECT.from_address(lp)
            value.left += 8; value.right -= 8; value.top += 31; value.bottom -= 8
            return 0
        self.backend.default = default
        self.hook.dispatch(123, chrome.WM_NCCALCSIZE, 1, ctypes.addressof(rect))
        self.assertEqual((rect.left, rect.top, rect.right, rect.bottom), (108, 200, 892, 792))

    def test_maximized_nonclient_top_accounts_for_invisible_resize_border(self):
        self.backend.maximized = True
        rect = chrome.RECT(-8, -8, 1928, 1040)
        def default(hwnd, msg, wp, lp):
            value = chrome.RECT.from_address(lp)
            value.left += 8; value.right -= 8; value.top += 31; value.bottom -= 8
            return 0
        self.backend.default = default
        self.hook.dispatch(123, chrome.WM_NCCALCSIZE, 1, ctypes.addressof(rect))
        self.assertEqual(rect.top, 0)

    def test_work_area_and_minimum_are_applied_without_real_windows(self):
        info = chrome.MINMAXINFO()
        self.hook.dispatch(123, chrome.WM_GETMINMAXINFO, 0, ctypes.addressof(info))
        self.assertEqual(info.ptMaxSize.y, 1040)
        self.assertEqual(info.ptMinTrackSize.x, 800)

    def test_dispose_is_idempotent_and_restores_native_frame(self):
        self.hook.dispose(); self.hook.dispose()
        self.assertEqual(self.backend.calls.count(('remove', 123)), 1)
        self.assertIn(('extend', False), self.backend.calls)

    def test_callback_exception_delegates_instead_of_escaping_into_ctypes(self):
        self.hook.caption = lambda: (_ for _ in ()).throw(RuntimeError('gone'))
        self.assertEqual(self.hook.dispatch(123, chrome.WM_NCHITTEST, 0, 0), 73)

    def test_destroy_detaches_without_frame_operations_on_dead_window(self):
        self.hook.dispatch(123, chrome.WM_NCDESTROY, 0, 0)
        self.assertFalse(self.hook.installed)
        self.assertEqual(self.backend.calls.count(('remove', 123)), 1)


class TkChromeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.closed = []
        with patch.object(chrome, '_make_backend', return_value=None):
            self.chrome = chrome.WindowChrome(self.root, lambda: self.closed.append(True))
        self.addCleanup(self.chrome.dispose)

    def test_fallback_keeps_normal_native_window_and_hides_duplicate_bar(self):
        self.assertFalse(self.root.overrideredirect())
        self.assertEqual(self.chrome.titlebar.winfo_manager(), '')
        self.assertFalse(self.chrome.native_active)

    def test_buttons_are_real_focusable_controls_and_close_uses_callback(self):
        self.chrome.close_button.invoke()
        self.root.update_idletasks()  # Close delivery deliberately leaves the native callback stack.
        self.assertEqual(self.closed, [True])
        for button in self.chrome.buttons:
            self.assertEqual(str(button.cget('takefocus')), '1')
        self.assertTrue(self.root.winfo_exists())

    def test_theme_event_reads_only_root_palette(self):
        self.root._droidbridge_palette = dict(background='#10231C', text='#F5F7FC', active='#214133', primary='#176B46')
        self.chrome.refresh_theme()
        self.assertEqual(self.chrome.titlebar.cget('background'), '#10231C')
        self.assertEqual(self.chrome.close_button.cget('foreground'), '#F5F7FC')

    def test_fake_native_attachment_packs_before_client_and_preserves_minimum(self):
        self.chrome.dispose()
        self.root.minsize(800, 600)
        client = tk.Frame(self.root); client.pack(fill='both', expand=True)
        backend = FakeBackend()
        with patch.object(chrome, '_make_backend', return_value=backend):
            attached = chrome.WindowChrome(self.root, lambda: self.closed.append(True))
        self.addCleanup(attached.dispose)
        with patch.object(self.root, 'winfo_ismapped', return_value=True):
            self.root.update_idletasks()
        self.assertTrue(attached.native_active)
        self.assertIs(self.root.pack_slaves()[0], attached.titlebar)
        self.assertEqual(self.root.minsize(), (800, 600))
        attached.minimize_button.invoke()
        attached.maximize_button.invoke()
        backend.maximized = True
        attached.maximize_button.invoke()
        self.assertEqual([call for call in backend.calls if call[0] == 'show'],
                         [('show', 6), ('show', 3), ('show', 9)])
        backend.maximized = False
        from types import SimpleNamespace
        attached._resize_press(SimpleNamespace(x_root=1, y_root=300))
        self.assertIn(('drag', 10), backend.calls)

    def test_scaled_titlebar_fits_intrinsic_button_height(self):
        self.root.tk.call('tk', 'scaling', 3.0)
        self.chrome.refresh_theme()
        self.root.update_idletasks()
        from tkinter import font
        metrics = font.Font(root=self.root, font=self.chrome.close_button.cget('font')).metrics('linespace')
        self.assertGreaterEqual(int(self.chrome.titlebar.cget('height')), metrics + 12)

    def test_native_callback_uses_cached_state_without_entering_tcl(self):
        self.chrome.backend = FakeBackend()
        self.chrome.backend.cursor = lambda: (760, 20)
        self.chrome._caption_height = 40
        self.chrome._button_rects = [(700, 0, 800, 40)]
        with patch.object(self.root, 'winfo_pointerxy', side_effect=AssertionError('Tcl reentry')):
            self.assertEqual(self.chrome._caption(), (40, True))
            self.chrome._native_close()
        self.assertEqual(self.closed, [])
        self.chrome._poll_native()
        self.root.update_idletasks()
        self.assertEqual(self.closed, [True])

    def test_failed_native_attachment_leaves_os_caption_and_client_usable(self):
        self.chrome.dispose()
        backend = FakeBackend()
        backend.frame_changed = lambda hwnd: (_ for _ in ()).throw(OSError('DWM unavailable'))
        with patch.object(chrome, '_make_backend', return_value=backend):
            attached = chrome.WindowChrome(self.root, lambda: None)
        self.addCleanup(attached.dispose)
        with patch.object(self.root, 'winfo_ismapped', return_value=True):
            self.root.update_idletasks()
        self.assertFalse(attached.native_active)
        self.assertFalse(self.root.overrideredirect())
        self.assertEqual(attached.titlebar.winfo_manager(), '')
        self.assertEqual(backend.calls.count(('remove', 123)), 1)

    @unittest.skipUnless(chrome.sys.platform == 'win32', 'Windows ctypes declarations')
    def test_real_win32_backend_loads_pointer_safe_api_without_opening_windows(self):
        backend = chrome._make_backend()
        self.assertIsNotNone(backend)
        self.assertEqual(backend.comctl.DefSubclassProc.restype, ctypes.c_ssize_t)
        self.assertEqual(backend.user.GetAncestor.restype, ctypes.wintypes.HWND)

    @unittest.skipUnless(chrome.sys.platform == 'win32', 'Windows native lifecycle')
    def test_native_lifecycle_in_isolated_subprocess_without_owner_window(self):
        import subprocess
        import sys
        script = '''
import ctypes
import tkinter as tk
from desktop.window_chrome import WindowChrome, MINMAXINFO, WM_GETMINMAXINFO
root = tk.Tk()
root.withdraw()
root.geometry('800x600+30000+30000')
root.minsize(800, 600)
closed = []
chrome = WindowChrome(root, lambda: closed.append(True))
root.deiconify()
root.update()
assert chrome.native_active, getattr(chrome, 'native_error', 'native chrome failed to attach')
for scale in (1.0, 2.0, 3.0, 1.33):
    root.tk.call('tk', 'scaling', scale)
    root.geometry('800x600+30000+30000')
    root.update()
info = MINMAXINFO()
chrome.backend.user.SendMessageW(chrome.hook.hwnd, WM_GETMINMAXINFO, 0, ctypes.addressof(info))
assert info.ptMinTrackSize.x == 800
chrome.backend.show(chrome.hook.hwnd, 3)
root.update()
monitor, work = chrome.backend.monitor(chrome.hook.hwnd)
assert root.winfo_rooty() >= work[1], (root.winfo_rooty(), work)
assert chrome.titlebar.winfo_rooty() >= work[1]
assert chrome.close_button.winfo_rooty() >= work[1]
assert root.winfo_rooty() + root.winfo_height() <= work[3]
chrome.minimize()
chrome.backend.show(chrome.hook.hwnd, 9)
root.update()
chrome.backend.user.SendMessageW(chrome.hook.hwnd, 0x10, 0, 0)
assert chrome._native_close_pending
chrome._poll_native()
root.update_idletasks()
assert closed == [True] and root.winfo_exists()
chrome.dispose()
chrome.dispose()
root.destroy()
print('native-lifecycle-ok')
'''
        result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('native-lifecycle-ok', result.stdout)

    def test_dispose_removes_owned_bindings_and_is_repeatable(self):
        self.chrome.dispose(); self.chrome.dispose()
        self.assertTrue(self.chrome._disposed)


if __name__ == '__main__':
    unittest.main()
