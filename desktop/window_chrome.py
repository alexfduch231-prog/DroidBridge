"""Optional Windows client-area titlebar, preserving the native Tk top-level.

No overrideredirect, global hooks, settings writes or third-party dependencies.
SetWindowSubclass keeps Tk's WndProc chain intact; failure leaves the OS caption.
The owning Tk thread must create and dispose this object.
"""
import ctypes
from ctypes import wintypes as wt
import sys
import tkinter as tk
from tkinter import font as tkfont

WM_CLOSE = 0x0010
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCDESTROY = 0x0082
HTCLIENT, HTCAPTION = 1, 2
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int32), ('y', ctypes.c_int32)]


class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_int32), ('top', ctypes.c_int32),
                ('right', ctypes.c_int32), ('bottom', ctypes.c_int32)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [('ptReserved', POINT), ('ptMaxSize', POINT), ('ptMaxPosition', POINT),
                ('ptMinTrackSize', POINT), ('ptMaxTrackSize', POINT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', RECT), ('rcWork', RECT), ('dwFlags', wt.DWORD)]


def point_from_lparam(value):
    return ctypes.c_int16(value & 0xffff).value, ctypes.c_int16((value >> 16) & 0xffff).value


def hit_test(point, rect, border, caption_height, *, interactive=False, maximized=False):
    x, y = point
    left, top, right, bottom = rect
    if not (left <= x < right and top <= y < bottom):
        return HTCLIENT
    if not maximized:
        l, r = x < left + border, x >= right - border
        t, b = y < top + border, y >= bottom - border
        if t: return 13 if l else 14 if r else 12
        if b: return 16 if l else 17 if r else 15
        if l: return 10
        if r: return 11
    if y < top + caption_height and not interactive:
        return HTCAPTION
    return HTCLIENT


def apply_work_area(info, monitor, work, minimum):
    info.ptMaxPosition = POINT(work[0] - monitor[0], work[1] - monitor[1])
    info.ptMaxSize = POINT(work[2] - work[0], work[3] - work[1])
    info.ptMinTrackSize = POINT(*minimum)
    info.ptMaxTrackSize = POINT(max(info.ptMaxTrackSize.x, info.ptMaxSize.x),
                                max(info.ptMaxTrackSize.y, info.ptMaxSize.y))


# Retain callbacks even if a failed detach leaves a native reference alive.
_LIVE_HOOKS = {}


class NativeHook:
    """Small testable message policy, independent of Tk and actual Win32 calls."""
    def __init__(self, backend, hwnd, on_close, caption, minimum):
        self.backend, self.hwnd = backend, hwnd
        self.on_close, self.caption, self.minimum = on_close, caption, minimum
        self.installed = False
        self.callback = None

    def install(self):
        self.callback = self.backend.install(self.hwnd, self.dispatch)
        self.installed = True
        _LIVE_HOOKS[id(self)] = self
        try:
            self.backend.extend(self.hwnd, True)
            self.backend.frame_changed(self.hwnd)
        except Exception:
            self.dispose()
            raise

    def dispatch(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_NCDESTROY:
                # No frame changes once Windows starts destroying the handle.
                self._detach()
            elif self.installed:
                if msg == WM_NCCALCSIZE and wp:
                    rect = RECT.from_address(lp)  # First NCCALCSIZE_PARAMS member.
                    top, left = rect.top, rect.left
                    self.backend.default(hwnd, msg, wp, lp)
                    # Remove only the caption. Retaining native side/bottom
                    # sizing borders also preserves Tk's client-size math.
                    # Maximized outer rect extends past the work area by the
                    # invisible resize frame; keep that inset at the top too.
                    rect.top = top + (rect.left - left if self.backend.is_zoomed(hwnd) else 0)
                    return 0
                if msg == WM_CLOSE:
                    self.on_close()
                    return 0
                if msg == WM_NCHITTEST:
                    height, interactive = self.caption()
                    return hit_test(point_from_lparam(lp), self.backend.rect(hwnd),
                                    max(5, round(8 * self.backend.dpi(hwnd) / 96)), height,
                                    interactive=interactive, maximized=self.backend.is_zoomed(hwnd))
                if msg == WM_GETMINMAXINFO:
                    self.backend.default(hwnd, msg, wp, lp)
                    monitor, work = self.backend.monitor(hwnd)
                    apply_work_area(MINMAXINFO.from_address(lp), monitor, work, self.minimum())
                    return 0
        except Exception:
            # Python exceptions must never escape a Windows callback boundary.
            pass
        return self.backend.default(hwnd, msg, wp, lp)

    def _detach(self):
        if self.installed:
            self.backend.remove(self.hwnd, self.callback)
            self.installed = False
            _LIVE_HOOKS.pop(id(self), None)

    def dispose(self):
        if not self.installed:
            return
        self._detach()
        self.backend.extend(self.hwnd, False)
        self.backend.frame_changed(self.hwnd)


class _Win32:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.comctl = ctypes.WinDLL('comctl32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        ptr, uint, lp = ctypes.c_size_t, wt.UINT, ctypes.c_ssize_t
        self.proc_type = ctypes.WINFUNCTYPE(lp, wt.HWND, uint, ptr, lp, ptr, ptr)
        self._declare(self.comctl.SetWindowSubclass, wt.BOOL, wt.HWND, self.proc_type, ptr, ptr)
        self._declare(self.comctl.RemoveWindowSubclass, wt.BOOL, wt.HWND, self.proc_type, ptr)
        self._declare(self.comctl.DefSubclassProc, lp, wt.HWND, uint, ptr, lp)
        self._declare(self.user.GetAncestor, wt.HWND, wt.HWND, uint)
        self._declare(self.user.GetWindowRect, wt.BOOL, wt.HWND, ctypes.POINTER(RECT))
        self._declare(self.user.IsZoomed, wt.BOOL, wt.HWND)
        self._declare(self.user.ShowWindow, wt.BOOL, wt.HWND, ctypes.c_int)
        self._declare(self.user.SetWindowPos, wt.BOOL, wt.HWND, wt.HWND, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, ctypes.c_int, uint)
        self._declare(self.user.MonitorFromWindow, wt.HANDLE, wt.HWND, wt.DWORD)
        self._declare(self.user.GetMonitorInfoW, wt.BOOL, wt.HANDLE, ctypes.POINTER(MONITORINFO))
        self._declare(self.user.SendMessageW, lp, wt.HWND, uint, ptr, lp)
        self._declare(self.user.PostMessageW, wt.BOOL, wt.HWND, uint, ptr, lp)
        self._declare(self.user.ReleaseCapture, wt.BOOL)
        self._declare(self.user.GetSystemMenu, wt.HMENU, wt.HWND, wt.BOOL)
        self._declare(self.user.TrackPopupMenu, uint, wt.HMENU, uint, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p)
        self._declare(self.user.GetCursorPos, wt.BOOL, ctypes.POINTER(POINT))
        long_get = 'GetWindowLongPtrW' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'GetWindowLongW'
        self.get_long = getattr(self.user, long_get)
        self._declare(self.get_long, lp, wt.HWND, ctypes.c_int)
        # Keep the original style: native resizing/system menu/taskbar remain.
        self._declare(self.dwm.DwmExtendFrameIntoClientArea, ctypes.c_long, wt.HWND, ctypes.c_void_p)
        if hasattr(self.user, 'GetDpiForWindow'):
            self._declare(self.user.GetDpiForWindow, uint, wt.HWND)

    @staticmethod
    def _declare(fn, result, *args):
        fn.restype, fn.argtypes = result, args

    def handle(self, root):
        hwnd = self.user.GetAncestor(root.winfo_id(), 2)
        if not hwnd: raise ctypes.WinError(ctypes.get_last_error())
        required = 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000
        if self.get_long(hwnd, -16) & required != required:
            raise OSError('Tk window does not have a normal resizable native frame')
        return hwnd

    def install(self, hwnd, dispatch):
        callback = self.proc_type(lambda h, m, w, l, _id, _data: dispatch(h, m, w, l))
        if not self.comctl.SetWindowSubclass(hwnd, callback, id(self), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return callback

    def remove(self, hwnd, callback):
        if not self.comctl.RemoveWindowSubclass(hwnd, callback, id(self)):
            raise OSError('Unable to detach window subclass')

    def default(self, hwnd, msg, wp, lp):
        return self.comctl.DefSubclassProc(hwnd, msg, wp, lp)

    def extend(self, hwnd, enabled):
        margins = (ctypes.c_int * 4)(0, 0, 1 if enabled else 0, 0)
        result = self.dwm.DwmExtendFrameIntoClientArea(hwnd, margins)
        if enabled and result < 0: raise OSError('DWM client frame extension failed')

    def frame_changed(self, hwnd):
        if not self.user.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0027):
            raise ctypes.WinError(ctypes.get_last_error())

    def rect(self, hwnd):
        rect = RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)): raise ctypes.WinError()
        return rect.left, rect.top, rect.right, rect.bottom

    def dpi(self, hwnd):
        return self.user.GetDpiForWindow(hwnd) or 96 if hasattr(self.user, 'GetDpiForWindow') else 96

    def is_zoomed(self, hwnd): return bool(self.user.IsZoomed(hwnd))

    def monitor(self, hwnd):
        info = MONITORINFO(); info.cbSize = ctypes.sizeof(info)
        handle = self.user.MonitorFromWindow(hwnd, 2)
        if not self.user.GetMonitorInfoW(handle, ctypes.byref(info)): raise ctypes.WinError()
        def values(r): return r.left, r.top, r.right, r.bottom
        return values(info.rcMonitor), values(info.rcWork)

    def show(self, hwnd, command): self.user.ShowWindow(hwnd, command)

    def cursor(self):
        point = POINT()
        self.user.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def drag(self, hwnd, region=HTCAPTION):
        self.user.ReleaseCapture()
        self.user.SendMessageW(hwnd, 0x00A1, region, 0)

    def system_menu(self, hwnd):
        point = POINT(); self.user.GetCursorPos(ctypes.byref(point))
        menu = self.user.GetSystemMenu(hwnd, False)
        command = self.user.TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, hwnd, None)
        if command: self.user.PostMessageW(hwnd, 0x0112, command, 0)


def _make_backend():
    if sys.platform != 'win32': return None
    try:
        return _Win32()
    except (OSError, AttributeError):
        return None


class _Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.timer, self.popup = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<FocusIn>', self.schedule, add='+')
        for event in ('<Leave>', '<FocusOut>', '<ButtonPress>', '<Destroy>'):
            widget.bind(event, self.hide, add='+')

    def schedule(self, _event=None):
        self.hide()
        self.timer = self.widget.after(650, self.show)

    def show(self):
        self.timer = None
        try:
            self.popup = tk.Toplevel(self.widget)
            self.popup.withdraw(); self.popup.overrideredirect(True)
            tk.Label(self.popup, text=self.text, background='#202530', foreground='#FFFFFF',
                     padx=8, pady=5).pack()
            self.popup.geometry('+%d+%d' % (self.widget.winfo_rootx(),
                                           self.widget.winfo_rooty() + self.widget.winfo_height()))
            self.popup.deiconify()
        except tk.TclError:
            self.hide()

    def hide(self, _event=None):
        if self.timer is not None:
            try: self.widget.after_cancel(self.timer)
            except tk.TclError: pass
            self.timer = None
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup = None


class WindowChrome:
    """Create before packing client content; dispose before destroying the root.

    Unsupported systems and native attachment errors use the ordinary OS caption.
    Custom buttons are keyboard-focusable; Alt+Space opens the native system menu.
    Windows 11 hover Snap Layouts are not emulated (Win+arrows still work).
    """
    def __init__(self, root, on_close, *, title='PConDistance'):
        self.root, self.on_close = root, on_close
        self._disposed = False
        self.native_active = False
        self.backend = _make_backend()
        self.hook = None
        self._bindings = []
        self._attach_timer = None
        self._close_timer = None
        self._poll_timer = None
        self._native_close_pending = False
        self._caption_height = 40
        self._button_rects = []
        self._minimum = root.minsize()
        self._old_protocol = root.protocol('WM_DELETE_WINDOW')
        root.protocol('WM_DELETE_WINDOW', self._request_close)
        from desktop.theme import font_family
        self._font_family = font_family(root)
        self.titlebar = tk.Frame(root, height=40, borderwidth=0)
        self.titlebar.pack_propagate(False)
        self.title_label = tk.Label(self.titlebar, text=title, anchor='w', padx=14,
                                    font=(self._font_family, 10), takefocus=False)
        self.title_label.pack(side='left', fill='both', expand=True)
        self.buttons = []
        self.tooltips = []
        for text, command, tooltip in (('−', self.minimize, 'Свернуть'),
                                       ('□', self.toggle_maximize, 'Развернуть / восстановить'),
                                       ('×', self._request_close, 'Закрыть (Alt+F4)')):
            button = tk.Button(self.titlebar, text=text, command=command, takefocus=True,
                               width=4, borderwidth=0, relief='flat', highlightthickness=1,
                               font=(self._font_family, 12), cursor='arrow')
            self.buttons.append(button)
            self.tooltips.append(_Tooltip(button, tooltip))
        self.minimize_button, self.maximize_button, self.close_button = self.buttons
        for button in reversed(self.buttons): button.pack(side='right', fill='y')
        for widget in (self.titlebar, self.title_label):
            widget.bind('<ButtonPress-1>', self._drag)
            widget.bind('<Double-Button-1>', self._double_click)
            widget.bind('<ButtonPress-3>', self._system_menu)
        self._bind('<<DroidBridgeThemeChanged>>', self.refresh_theme)
        self._bind('<Destroy>', self._destroy)
        self._bind('<Map>', self._mapped)
        self._bind('<Configure>', self._configured)
        self._bind('<Alt-space>', self._system_menu)
        self._bind('<ButtonPress-1>', self._resize_press)
        self.refresh_theme()
        if self.backend is not None:
            self._attach_timer = root.after_idle(self._attach)

    def _bind(self, event, callback):
        self._bindings.append((event, self.root.bind(event, callback, add='+')))

    def _mapped(self, event):
        if event.widget is self.root and not self.native_active and not self._disposed and self.backend:
            if self._attach_timer is None:
                self._attach_timer = self.root.after_idle(self._attach)

    def _attach(self):
        self._attach_timer = None
        if self._disposed or self.native_active: return
        if not self.root.winfo_ismapped():
            return  # Tk's pre-map wrapper lacks its final native frame styles.
        try:
            geometry = self.root.geometry()
            hwnd = self.backend.handle(self.root)
            self.hook = NativeHook(self.backend, hwnd, self._native_close, self._caption,
                                   lambda: self._minimum)
            # Pack before recalculation so native hit-testing has valid title geometry.
            children = self.root.pack_slaves()
            options = dict(side='top', fill='x')
            if children: options['before'] = children[0]
            self.titlebar.pack(**options)
            self.hook.install()
            self.native_active = True
            self.root.geometry(geometry)
            self._cache_geometry()
            self._poll_timer = self.root.after(50, self._poll_native)
        except Exception as exc:
            self.native_error = str(exc)
            if self.hook is not None:
                try: self.hook.dispose()
                except Exception: pass
            self.titlebar.pack_forget()
            self.backend = None
            self.native_active = False

    def _cache_geometry(self):
        # Never call Tcl from a subclass callback: Windows can invoke it while
        # _tkinter temporarily releases its Tcl/Python thread context.
        self._minimum = self.root.minsize()
        self._fit_height()
        self._caption_height = self.titlebar.winfo_height()
        self._button_rects = [(b.winfo_rootx(), b.winfo_rooty(),
                               b.winfo_rootx() + b.winfo_width(),
                               b.winfo_rooty() + b.winfo_height()) for b in self.buttons]

    def _caption(self):
        x, y = self.backend.cursor()
        return self._caption_height, any(l <= x < r and t <= y < b
                                         for l, t, r, b in self._button_rects)

    def _native_close(self):
        self._native_close_pending = True

    def _poll_native(self):
        self._poll_timer = None
        if self._disposed: return
        if self._native_close_pending:
            self._native_close_pending = False
            self._request_close()
        self._cache_geometry()
        self._poll_timer = self.root.after(50, self._poll_native)

    def _resize_press(self, event):
        if not self.native_active: return
        region = hit_test((event.x_root, event.y_root), self.backend.rect(self.hook.hwnd),
                          max(5, round(8 * self.backend.dpi(self.hook.hwnd) / 96)), 0,
                          maximized=self.backend.is_zoomed(self.hook.hwnd))
        if region not in (HTCLIENT, HTCAPTION):
            self.backend.drag(self.hook.hwnd, region)
            return 'break'

    def _request_close(self):
        if not self._disposed and self._close_timer is None:
            # Leave the native callback stack before application teardown.
            self._close_timer = self.root.after_idle(self._deliver_close)

    def _deliver_close(self):
        self._close_timer = None
        if not self._disposed: self.on_close()

    def minimize(self):
        if self.native_active: self.backend.show(self.hook.hwnd, SW_MINIMIZE)
        else: self.root.iconify()

    def toggle_maximize(self):
        if self.native_active:
            self.backend.show(self.hook.hwnd, SW_RESTORE if self.backend.is_zoomed(self.hook.hwnd) else SW_MAXIMIZE)
        else:
            try: self.root.state('normal' if self.root.state() == 'zoomed' else 'zoomed')
            except tk.TclError: pass

    def _configured(self, event):
        if event.widget is self.root and self.native_active:
            self.maximize_button.configure(text='❐' if self.backend.is_zoomed(self.hook.hwnd) else '□')

    def _drag(self, _event):
        if self.native_active: self.backend.drag(self.hook.hwnd)
        return 'break'

    def _double_click(self, _event):
        self.toggle_maximize()
        return 'break'

    def _system_menu(self, _event=None):
        if self.native_active:
            self.backend.system_menu(self.hook.hwnd)
            return 'break'

    def _fit_height(self):
        metrics = tkfont.Font(root=self.root, font=self.close_button.cget('font')).metrics('linespace')
        height = max(40, metrics + 16, *(button.winfo_reqheight() for button in self.buttons))
        if int(self.titlebar.cget('height')) != height:
            self.titlebar.configure(height=height)

    def refresh_theme(self, _event=None):
        self._fit_height()
        p = getattr(self.root, '_droidbridge_palette', None)
        if p is None:
            p = getattr(getattr(self.root, 'theme_controller', None), 'palette', {})
        bg, fg = p.get('background', '#F1F3F8'), p.get('text', '#16181D')
        self.titlebar.configure(background=bg)
        self.title_label.configure(background=bg, foreground=fg)
        for button in self.buttons:
            close = button is self.close_button
            button.configure(background=bg, foreground=fg, activebackground='#C42B1C' if close else p.get('active', '#E9EFFB'),
                             activeforeground='#FFFFFF' if close else fg, highlightbackground=bg,
                             highlightcolor=p.get('primary', '#1A63E7'))

    def _destroy(self, event):
        if event.widget is self.root: self.dispose()

    def dispose(self):
        if self._disposed: return
        self._disposed = True
        for timer in (self._attach_timer, self._close_timer, self._poll_timer):
            if timer is not None:
                try: self.root.after_cancel(timer)
                except tk.TclError: pass
        self._attach_timer = self._close_timer = self._poll_timer = None
        for tooltip in self.tooltips: tooltip.hide()
        if self.hook is not None:
            try: self.hook.dispose()
            except (OSError, tk.TclError): pass
        self.native_active = False
        for event, binding in self._bindings:
            try: self.root.unbind(event, binding)
            except tk.TclError: pass
        self._bindings.clear()
        try:
            self.root.protocol('WM_DELETE_WINDOW', self._old_protocol)
            self.titlebar.pack_forget()
        except tk.TclError: pass
