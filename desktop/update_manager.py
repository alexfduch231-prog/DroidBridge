"""Voluntary GUI-only updates. All workers communicate with Tk through a queue."""
import hashlib
import http.client
import os
from pathlib import Path
import queue
import ssl
import tempfile
import threading
import time
import urllib.request
import webbrowser

from update_protocol import (CURRENT_VERSION, FEED_URL, MAX_ENVELOPE, REPOSITORY,
                             SequenceState, is_newer, validate_https_url, verify_manifest, validate_payload)


class Cancelled(Exception):
    pass


class RedirectPolicy(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_https_url(newurl)
        count = getattr(req, '_update_redirects', 0) + 1
        if count > 5:
            raise ValueError('too many redirects')
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is None:
            raise ValueError('unsupported redirect')
        result._update_redirects = count
        return result


class _Connection(http.client.HTTPSConnection):
    def connect(self):
        self.timeout = 10
        super().connect()
        self.sock.settimeout(20)


class _HTTPS(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(_Connection, request, context=ssl.create_default_context())


def make_opener():
    # Do not inherit proxy credentials, netrc, cookies or browser authentication.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), RedirectPolicy(), _HTTPS())


def open_url(url):
    validate_https_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'DroidBridge/' + CURRENT_VERSION,
                                                  'Accept': 'application/octet-stream'})
    return make_opener().open(request, timeout=10)


def _chunks(response, maximum, cancel, deadline, clock=time.monotonic):
    received = 0
    read = getattr(response, 'read1', response.read)
    while True:
        if cancel.is_set():
            raise Cancelled('download cancelled')
        if clock() >= deadline:
            raise ValueError('download deadline exceeded')
        chunk = read(min(64 * 1024, maximum + 1 - received))
        if clock() >= deadline:
            raise ValueError('download deadline exceeded')
        if not chunk:
            break
        received += len(chunk)
        if received > maximum:
            raise ValueError('download too large')
        yield chunk


def check_manifest(directory, *, opener=open_url, now=None):
    deadline = time.monotonic() + 60
    with opener(FEED_URL) as response:
        raw = b''.join(_chunks(response, MAX_ENVELOPE, threading.Event(), deadline))
    manifest = verify_manifest(raw, now=now)
    SequenceState(directory).accept(manifest['sequence'])
    return manifest


def download_asset(asset, directory, cancel, *, opener=open_url, progress=None):
    validate_https_url(asset['url'])
    size = asset['size']
    if type(size) is not int or not 1 <= size <= 512 * 1024 * 1024:
        raise ValueError('invalid download size')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='update-', suffix='.part', dir=directory)
    destination = Path(temporary).with_suffix('.exe')
    deadline = time.monotonic() + 600
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as output:
            with opener(asset['url']) as response:
                for chunk in _chunks(response, size, cancel, deadline):
                    output.write(chunk)
                    count += len(chunk)
                    digest.update(chunk)
                    if progress:
                        progress(count, size)
            output.flush()
            os.fsync(output.fileno())
        if cancel.is_set():
            raise Cancelled('download cancelled')
        if count != size or digest.hexdigest() != asset['sha256']:
            raise ValueError('installer size or SHA256 mismatch')
        os.replace(temporary, destination)
        return destination
    finally:
        Path(temporary).unlink(missing_ok=True)


_started = False


def start_startup_check(root, directory, shutdown_signal):
    """Call only after ordinary GUI creation, never from self-test/components."""
    global _started
    if _started:
        return None
    _started = True
    controller = UpdateController(root, directory, shutdown_signal)
    controller.start()
    return controller


class UpdateController:
    def __init__(self, root, directory, shutdown_signal):
        self.root, self.directory, self.shutdown_signal = root, Path(directory), shutdown_signal
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.alive = True
        self.window = None
        self.timer = None
        self.root.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget is self.root:
            self.alive = False
            self.cancel.set()
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None

    def start(self):
        def worker():
            try:
                manifest = check_manifest(self.directory)
                if is_newer(manifest['windows']['version']):
                    self.events.put(('available', manifest))
            except Exception:
                # Offline, bad signatures, corrupt local state: normal GUI continues.
                pass
        threading.Thread(target=worker, name='update-check', daemon=True).start()
        self.timer = self.root.after(100, self._drain)

    def _drain(self):
        if not self.alive:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'available':
                    self._offer(value)
                elif kind == 'progress' and self.window:
                    self.progress['value'] = value
                elif kind == 'downloaded':
                    self._ready(value)
                elif kind == 'failed':
                    self._finish_error(value)
        except queue.Empty:
            pass
        if self.alive:
            self.timer = self.root.after(100, self._drain)

    def _offer(self, manifest):
        import tkinter as tk
        from tkinter import ttk
        try:
            from theme import apply_theme
        except ModuleNotFoundError:
            from desktop.theme import apply_theme
        dialog = tk.Toplevel(self.root)
        apply_theme(dialog)
        dialog.title('DroidBridge update')
        dialog.transient(self.root)
        self.window = dialog
        ttk.Label(dialog, style='DB.TLabel', text='Доступна версия ' + manifest['windows']['version'] +
                  '.\nОбновление добровольное. Настройки и ключи сохранятся.', padding=16).pack()
        row = ttk.Frame(dialog, padding=20, style='DB.Card.TFrame')
        row.pack()
        def accept():
            import sys
            if not getattr(sys, 'frozen', False):
                # Source checkout has no trustworthy installed binary to replace.
                # Explicit click opens only this fixed public releases page.
                webbrowser.open('https://github.com/' + REPOSITORY + '/releases/latest')
                dialog.destroy()
                self.window = None
                return
            from tkinter import messagebox
            if not messagebox.askyesno('Остановить DroidBridge для обновления?',
                    'После загрузки будут закрыты все окна DroidBridge из этой установки, сервер и просмотр. '
                    'Текущие передачи файлов прервутся; дождись их завершения, если это важно. '
                    'После успешной установки откроется только главное окно, без запуска сервера. Продолжить?', parent=dialog):
                return
            for child in row.winfo_children():
                child.destroy()
            self.progress = ttk.Progressbar(dialog, maximum=100, length=320)
            self.progress.pack(padx=16, pady=8)
            ttk.Button(row, text='Cancel', command=self.cancel.set).pack()
            dialog.protocol('WM_DELETE_WINDOW', self.cancel.set)
            def worker():
                try:
                    validate_payload(manifest)
                    SequenceState(self.directory).accept(manifest['sequence'])
                    asset = manifest['windows']
                    path = download_asset(asset, self.directory / 'updates', self.cancel,
                                          progress=lambda n, total: self.events.put(('progress', 100 * n / total)))
                    self.events.put(('downloaded', (path, manifest)))
                except Exception as error:
                    self.events.put(('failed', str(error)))
            threading.Thread(target=worker, name='update-download', daemon=True).start()
        ttk.Button(row, style='DB.Primary.TButton', text='Update', command=accept).pack(side='left')
        ttk.Button(row, text='Not now', command=dialog.destroy).pack(side='left', padx=8)

    def _ready(self, value):
        from update_helper import launch_helper
        import sys
        path, manifest = value
        asset = manifest['windows']
        if self.cancel.is_set() or not self.alive:
            path.unlink(missing_ok=True)
            self._finish_error('Обновление отменено.')
            return
        try:
            validate_payload(manifest)
            SequenceState(self.directory).accept(manifest['sequence'])
            if self.shutdown_signal is None:
                raise ValueError('Safe coordinated shutdown unavailable')
            # The helper signals shutdown only AFTER re-verifying and locking the
            # installer. GUI stays alive if spawning it fails.
            launch_helper(Path(sys.executable).resolve(), path, asset['sha256'], asset['size'],
                          sequence=manifest['sequence'], expires=manifest['expiresAt'])
        except Exception as error:
            path.unlink(missing_ok=True)
            self._finish_error(str(error))

    def _finish_error(self, text):
        from tkinter import messagebox
        if self.window:
            self.window.destroy()
            self.window = None
        if self.alive and not self.cancel.is_set():
            messagebox.showerror('Обновление не установлено', text, parent=self.root)
