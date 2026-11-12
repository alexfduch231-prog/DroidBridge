"""Frozen/source dispatch without installing Python on an end user's PC."""
import importlib.util
import ipaddress
import os
from pathlib import Path
import subprocess
import sys


def data_directory(environment=None):
    env = os.environ if environment is None else environment
    return Path(env.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'VzaimoPult'


def phone_address(value):
    return str(ipaddress.ip_address(value.strip()))


def bundle_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def child_command(component, *arguments):
    if component not in ('server', 'viewer'):
        raise ValueError('Unknown component')
    base = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('launcher.py'))]
    return base + ['--component', component, *arguments]


def start_child(component, *arguments):
    return subprocess.Popen(child_command(component, *arguments), env=os.environ.copy(),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def load_component(component):
    if component not in ('server', 'viewer'):
        raise ValueError('Unknown component')
    root = bundle_root()
    relative = 'listener/pc-listener.py' if component == 'server' else 'client/pc-viewer.pyw'
    path = root / relative
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('vzaimopult_' + component, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_component(component, arguments):
    data = data_directory()
    data.mkdir(parents=True, exist_ok=True)
    os.environ['VZAIMOPULT_DATA_DIR'] = str(data)
    signal = create_update_signal()
    if signal is not None and signal.is_set():
        signal.close()
        return 0
    module = load_component(component)
    if signal is not None:
        coordinate_component_shutdown(module, component, signal)
    # Compatibility with versions predating the production environment override.
    if component == 'server':
        module.TOKEN_FILE = str(data / 'token.txt')
        module.APPS_FILE = str(data / 'apps.json')
        module.LOG_FILE = str(data / 'listener.log')
        module.CLIENT_PID = str(data / 'client.pid')
        from desktop.mirror_handoff import request_mirror
        def mirror(ip, port):
            return request_mirror(data, ip, port)
        module.start_mirror_client = mirror
        # Embedded GUI sessions have no standalone PID. Always deliver the
        # authenticated request, even if an old client.pid points to a live PID.
        module.client_alive = lambda: False
    else:
        module.LOG_PATH = str(data / 'client.log')
        module.PID_PATH = str(data / 'client.pid')
        module.DEFAULT_TOKEN = str(data / 'token.txt')
    sys.argv = [sys.argv[0], *arguments]
    try:
        return module.main()
    finally:
        if signal is not None:
            signal.close()


class UpdateShutdownSignal:
    """Manual reset Win32 event shared only by the same installed binary path."""
    def __init__(self, name):
        import ctypes
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        for method in ('SetEvent', 'ResetEvent', 'CloseHandle'):
            getattr(self.kernel, method).argtypes = [wintypes.HANDLE]
            getattr(self.kernel, method).restype = wintypes.BOOL
        self.handle = self.kernel.CreateEventW(None, True, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def is_set(self):
        return self.wait(0)

    def wait(self, timeout):
        result = self.kernel.WaitForSingleObject(self.handle, int(timeout * 1000))
        if result == 0:
            return True
        if result == 258:
            return False
        raise OSError('Update shutdown event unavailable')

    def set(self):
        if not self.kernel.SetEvent(self.handle):
            raise OSError('Cannot signal update shutdown')

    def reset(self):
        if not self.kernel.ResetEvent(self.handle):
            raise OSError('Cannot reset update shutdown')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def create_update_signal():
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return None
    from update_helper import event_name
    return UpdateShutdownSignal(event_name(Path(sys.executable).resolve()))


def coordinate_component_shutdown(module, component, signal):
    """Adapt loaded component entrypoints without touching frozen media/UI code."""
    import threading
    if component == 'server':
        original = module.Server
        class CoordinatedServer(original):
            # server_close waits for handlers, including in-flight upload cleanup.
            daemon_threads = False
            block_on_close = True

            def serve_forever(self, *args, **kwargs):
                finished = threading.Event()
                def monitor():
                    while not finished.is_set():
                        if signal.wait(0.2):
                            self.shutdown()
                            return
                threading.Thread(target=monitor, name='update-server-stop', daemon=True).start()
                try:
                    return super().serve_forever(*args, **kwargs)
                finally:
                    finished.set()
        module.Server = CoordinatedServer
    else:
        original = module.Viewer
        class CoordinatedViewer(original):
            def __init__(self, root, *args, **kwargs):
                super().__init__(root, *args, **kwargs)
                def poll_update():
                    if signal.is_set():
                        self.close()
                    else:
                        root.after(200, poll_update)
                root.after(200, poll_update)
        module.Viewer = CoordinatedViewer
