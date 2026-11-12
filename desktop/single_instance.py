"""Per-user, per-data-directory Windows GUI reservation and activation.

No sockets, files, process enumeration, native callbacks or worker threads.
Other platforms deliberately run normally without enforcing a singleton.
Foreground activation is best effort: Windows may refuse focus stealing.
"""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys


class _Windows:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        signatures = (
            (self.kernel, 'GetCurrentProcess', [], wintypes.HANDLE),
            (self.kernel, 'CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, 'CreateMutexW', [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            (self.kernel, 'ReleaseMutex', [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, 'CreateEventW', [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            (self.kernel, 'SetEvent', [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, 'WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            (self.advapi, 'OpenProcessToken', [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
            (self.advapi, 'GetTokenInformation', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.advapi, 'GetLengthSid', [ctypes.c_void_p], wintypes.DWORD),
            (self.user, 'GetAncestor', [wintypes.HWND, wintypes.UINT], wintypes.HWND),
            (self.user, 'ShowWindow', [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            (self.user, 'SetForegroundWindow', [wintypes.HWND], wintypes.BOOL),
        )
        for library, name, args, result in signatures:
            function = getattr(library, name)
            function.argtypes, function.restype = args, result

    def user_sid(self):
        token = wintypes.HANDLE()
        if not self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wintypes.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not size.value:
                raise ctypes.WinError(ctypes.get_last_error())
            buffer = ctypes.create_string_buffer(size.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            # TOKEN_USER begins with SID_AND_ATTRIBUTES; the first member is PSID.
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            length = self.advapi.GetLengthSid(sid)
            if not length:
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.string_at(sid, length)
        finally:
            self.kernel.CloseHandle(token)


class SingleInstance:
    """Reserve before constructing Tk; close on the reserving GUI thread."""
    def __init__(self, data_dir):
        self.is_primary = True
        self._native = None
        self._mutex = self._event = None
        self._owned = False
        self._root = None
        self._timer = None
        self._closed = False
        if sys.platform != 'win32':
            return
        self._native = _Windows()
        native = self._native
        canonical = os.path.normcase(str(Path(data_dir).resolve()))
        digest = hashlib.sha256(native.user_sid() + b'\0' + canonical.encode('utf-8')).hexdigest()
        name = 'Local\\DroidBridge.GUI.' + digest
        try:
            # Event comes first: a second launch during Tk startup is retained.
            self._event = native.kernel.CreateEventW(None, False, False, name + '.activate')
            if not self._event:
                raise ctypes.WinError(ctypes.get_last_error())
            self._mutex = native.kernel.CreateMutexW(None, False, name + '.mutex')
            if not self._mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            state = native.kernel.WaitForSingleObject(self._mutex, 0)
            if state in (0, 0x80):  # acquired or abandoned by a crashed process
                self._owned = True
            elif state == 0x102:
                self.is_primary = False
                if not native.kernel.SetEvent(self._event):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def attach(self, root):
        """Poll only on Tk's own thread; never call Tcl from native code."""
        if self._closed or not self.is_primary or self._root is not None:
            return
        self._root = root
        root.bind('<Destroy>', self._destroyed, add='+')
        if self._native is not None:
            self._timer = root.after(100, self._poll)

    def _destroyed(self, event):
        if event.widget is self._root:
            self.close()

    def _poll(self):
        self._timer = None
        if self._closed:
            return
        state = self._native.kernel.WaitForSingleObject(self._event, 0)
        if state == 0:
            self._activate()
        if not self._closed:
            self._timer = self._root.after(100, self._poll)

    def _activate(self):
        # This is a regular Tk after callback, not a WndProc callback.
        root = self._root
        try:
            root.deiconify()
            hwnd = self._native.user.GetAncestor(root.winfo_id(), 2)
            if hwnd:
                self._native.user.ShowWindow(hwnd, 9)  # SW_RESTORE
            root.lift()
            root.focus_force()
            if hwnd:
                self._native.user.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Destroy/focus races cannot stop the GUI event loop.

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            try:
                self._root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        if self._native is not None:
            if self._event:
                self._native.kernel.CloseHandle(self._event)
                self._event = None
            if self._mutex:
                if self._owned:
                    self._native.kernel.ReleaseMutex(self._mutex)
                    self._owned = False
                self._native.kernel.CloseHandle(self._mutex)
                self._mutex = None
