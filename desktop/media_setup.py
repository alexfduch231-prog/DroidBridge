"""Local, explicitly consented media setup. Tk is imported only when opened."""
from pathlib import Path
import queue
import sys
import threading

if not getattr(sys, 'frozen', False):
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)
from listener.media_tools import (MediaToolsError, resolve_media_tools,
                                  save_media_directory, reset_media_directory)


RESTART_NOTICE = 'Изменения применятся при новом запуске сервера и окна просмотра. Останови и запусти их заново; закрывать PConDistance не нужно.'


_jobs_lock = threading.Lock()
_jobs = {}


def _job_key(data_dir):
    return str(Path(data_dir).resolve()).casefold()


def _media_busy(data_dir):
    with _jobs_lock:
        return _job_key(data_dir) in _jobs


def start_media_setup(data_dir, directory, results) -> threading.Thread:
    """Run one consented validation/save per data directory, across page lifetimes."""
    key = _job_key(data_dir)
    with _jobs_lock:
        if key in _jobs:
            raise MediaToolsError('Проверка уже идёт. Дождись её завершения.')
        _jobs[key] = results

    def work():
        try:
            tools = save_media_directory(data_dir, directory)
            results.put((True, tools))
        except MediaToolsError as error:
            results.put((False, str(error)))
        except (OSError, ValueError):
            results.put((False, 'Не удалось настроить видео и звук. Проверь выбранную папку.'))
        finally:
            with _jobs_lock:
                _jobs.pop(key, None)
    worker = threading.Thread(target=work, name='media-setup', daemon=True)
    try:
        worker.start()
    except RuntimeError:
        with _jobs_lock:
            _jobs.pop(key, None)
        raise
    return worker


def build_media_page(parent, data_dir):
    """Build an unpacked media frame; validation survives hiding or disposal."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import webbrowser

    try:
        from theme import scrollable_card
    except ModuleNotFoundError:
        from desktop.theme import scrollable_card
    window = ttk.Frame(parent, style='DB.TFrame')
    frame = scrollable_card(window)
    ttk.Label(frame, text='Видео H.264 и звук: FFmpeg / ffplay', style='DB.Heading.TLabel').pack(anchor='w')
    ttk.Label(frame, style='DB.Muted.TLabel', text='Обычная установка PConDistance уже содержит инструменты видео и звука. '
              'Они выбираются автоматически — менять PATH не нужно. '
              'Здесь можно выбрать другую сборку вручную или вернуть автоматический поиск.', wraplength=620).pack(anchor='w', pady=10)
    ttk.Label(frame, style='DB.Danger.TLabel', text='Это исполняемые программы. После твоего подтверждения PConDistance запустит '
              'оба файла с -version для проверки (до 5 секунд на каждый), а затем будет использовать '
              'их для видео и звука. Выбирай только сборку из доверенного источника.', wraplength=620).pack(anchor='w')
    current = tk.StringVar(master=window)
    entry = ttk.Entry(frame, textvariable=current, state='readonly')
    entry.pack(fill='x', pady=(12, 0))
    scroll = ttk.Scrollbar(frame, orient='horizontal', command=entry.xview)
    entry.configure(xscrollcommand=scroll.set)
    scroll.pack(fill='x')
    status = tk.StringVar(master=window, value=RESTART_NOTICE)
    ttk.Label(frame, style='DB.Muted.TLabel', textvariable=status, wraplength=620).pack(anchor='w', pady=10)
    results = queue.Queue()
    busy = [False]
    disposed = [False]
    pending_poll = [None]

    def cleanup(event=None):
        if event is not None and event.widget is not window:
            return
        disposed[0] = True
        if pending_poll[0] is not None:
            try:
                window.after_cancel(pending_poll[0])
            except tk.TclError:
                pass
            pending_poll[0] = None

    def dispose():
        cleanup()
        if window.winfo_exists():
            window.destroy()

    window.dispose = dispose
    window.bind('<Destroy>', cleanup, add='+')

    def refresh():
        try:
            tools = resolve_media_tools(data_dir)
            if tools.ffmpeg and tools.ffplay:
                labels = {
                    'configured': 'Выбраны вручную',
                    'distribution': 'В комплекте PConDistance',
                    'path': 'Найдены в PATH',
                    'detected': 'Найдены на компьютере',
                }
                source = labels.get(tools.source, 'Найдены автоматически')
                current.set(f'{source}: {Path(tools.ffmpeg).parent}')
            else:
                current.set('Инструменты не найдены — восстанови установку или выбери папку bin')
        except MediaToolsError:
            current.set('Выбранная папка или настройки недоступны — выбери заново или сбрось')

    def set_busy(value):
        busy[0] = value
        for button in (choose, reset):
            button.configure(state='disabled' if value else 'normal')

    def poll():
        pending_poll[0] = None
        if disposed[0]:
            return
        try:
            success, result = results.get_nowait()
        except queue.Empty:
            if _media_busy(data_dir):
                set_busy(True)
                pending_poll[0] = window.after(75, poll)
            else:
                set_busy(False)
                refresh()
                status.set(RESTART_NOTICE)
            return
        set_busy(False)
        if success:
            refresh()
            status.set('Проверка пройдена, папка сохранена. ' + RESTART_NOTICE)
        else:
            status.set('Настройки не изменены. ' + RESTART_NOTICE)
            messagebox.showerror('Не удалось настроить видео и звук', result, parent=window)

    def select():
        if _media_busy(data_dir):
            return
        selected = filedialog.askdirectory(parent=window, mustexist=True,
                                            title='Выбери папку с ffmpeg.exe и ffplay.exe (или её родительскую папку)')
        if not selected:
            return
        if not messagebox.askyesno('Запустить выбранные программы для проверки?',
                'Будут запущены ffmpeg.exe и ffplay.exe из выбранной папки с параметром -version. '
                'Это исполняемые программы: продолжай, только если доверяешь их источнику.', parent=window):
            return
        set_busy(True)
        status.set('Проверяем оба файла… Окно остаётся доступным, проверка займёт до 10 секунд.')
        try:
            start_media_setup(data_dir, selected, results)
        except MediaToolsError:
            status.set('Проверка уже идёт. Дождись её завершения. ' + RESTART_NOTICE)
        pending_poll[0] = window.after(75, poll)

    def clear():
        if _media_busy(data_dir):
            return
        try:
            reset_media_directory(data_dir)
            refresh()
            status.set('Включён автоматический поиск инструментов видео и звука. ' + RESTART_NOTICE)
        except MediaToolsError as error:
            messagebox.showerror('Не удалось сбросить настройки', str(error), parent=window)

    row = ttk.Frame(frame, style='DB.Card.TFrame')
    row.pack(fill='x', pady=6)
    choose = ttk.Button(row, style='DB.Primary.TButton', text='Выбрать папку…', command=select)
    choose.pack(side='left')
    reset = ttk.Button(row, text='Автоматический поиск', command=clear)
    reset.pack(side='left', padx=8)
    ttk.Button(frame, text='Официальный сайт FFmpeg',
               command=lambda: webbrowser.open('https://ffmpeg.org/download.html')).pack(anchor='w', pady=6)
    refresh()
    window.close_container = row
    window.is_busy = lambda: busy[0] or _media_busy(data_dir)
    if _media_busy(data_dir):
        set_busy(True)
        status.set('Проверка уже идёт. Дождись её завершения. ' + RESTART_NOTICE)
        pending_poll[0] = window.after(75, poll)
    return window


def show_media_setup(parent, data_dir):
    """Compatibility wrapper around the embedded, explicitly consented setup."""
    import tkinter as tk
    from tkinter import ttk
    try:
        from theme import apply_theme
    except ModuleNotFoundError:
        from desktop.theme import apply_theme

    window = tk.Toplevel(parent)
    try:
        apply_theme(window)
        page = build_media_page(window, data_dir)
        window.title('Настроить видео и звук')
        window.geometry(f'730x{min(510, max(400, window.winfo_screenheight() - 100))}')
        window.minsize(520, 400)
        window.transient(parent)
        page.pack(fill='both', expand=True)
        def close():
            from tkinter import messagebox
            if page.is_busy():
                messagebox.showinfo('Идёт проверка', 'Дождись окончания проверки перед закрытием окна.', parent=window)
                return
            window.destroy()

        ttk.Button(page.close_container, text='Закрыть', command=close).pack(side='right')
        window.protocol('WM_DELETE_WINDOW', close)
    except Exception:
        window.destroy()
        raise
    return window
