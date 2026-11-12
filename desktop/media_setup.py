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


RESTART_NOTICE = 'Изменения применятся при новом запуске сервера и окна просмотра. Останови и запусти их заново; закрывать DroidBridge не нужно.'


def start_media_setup(data_dir, directory, results) -> threading.Thread:
    """Run probes and atomic save off the Tk thread; report through a queue."""
    def work():
        try:
            tools = save_media_directory(data_dir, directory)
            results.put((True, tools))
        except MediaToolsError as error:
            results.put((False, str(error)))
        except (OSError, ValueError):
            results.put((False, 'Не удалось настроить видео и звук. Проверь выбранную папку.'))
    worker = threading.Thread(target=work, name='media-setup', daemon=True)
    worker.start()
    return worker


def show_media_setup(parent, data_dir):
    """Open a local non-modal settings window; never run tools without consent."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import webbrowser

    window = tk.Toplevel(parent)
    window.title('Настроить видео и звук')
    window.geometry('690x430')
    window.minsize(650, 430)
    window.transient(parent)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Видео H.264 и звук: FFmpeg / ffplay', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='DroidBridge не включает FFmpeg и ничего не скачивает автоматически. '
              'С официального сайта выбери подходящую сборку, распакуй архив, выбери папку bin. '
              'В ней должны быть ffmpeg.exe и ffplay.exe. Менять PATH не нужно.', wraplength=620).pack(anchor='w', pady=10)
    ttk.Label(frame, text='Это исполняемые программы. После твоего подтверждения DroidBridge запустит '
              'оба файла с -version для проверки (до 5 секунд на каждый), а затем будет использовать '
              'их для видео и звука. Выбирай только сборку из доверенного источника.', wraplength=620).pack(anchor='w')
    current = tk.StringVar(master=window)
    entry = ttk.Entry(frame, textvariable=current, state='readonly')
    entry.pack(fill='x', pady=(12, 0))
    scroll = ttk.Scrollbar(frame, orient='horizontal', command=entry.xview)
    entry.configure(xscrollcommand=scroll.set)
    scroll.pack(fill='x')
    status = tk.StringVar(master=window, value=RESTART_NOTICE)
    ttk.Label(frame, textvariable=status, wraplength=620).pack(anchor='w', pady=10)
    results = queue.Queue()
    busy = [False]

    def refresh():
        try:
            tools = resolve_media_tools(data_dir)
            if tools.source == 'configured':
                current.set(str(Path(tools.ffmpeg).parent))
            elif tools.ffmpeg and tools.ffplay:
                current.set('Найдены автоматически: папка media или PATH')
            else:
                current.set('ffmpeg.exe и ffplay.exe не найдены — выбери папку bin')
        except MediaToolsError:
            current.set('Выбранная папка или настройки недоступны — выбери заново или сбрось')

    def set_busy(value):
        busy[0] = value
        for button in (choose, reset):
            button.configure(state='disabled' if value else 'normal')

    def poll():
        try:
            success, result = results.get_nowait()
        except queue.Empty:
            window.after(75, poll)
            return
        set_busy(False)
        if success:
            refresh()
            status.set('Проверка пройдена, папка сохранена. ' + RESTART_NOTICE)
        else:
            status.set('Настройки не изменены. ' + RESTART_NOTICE)
            messagebox.showerror('Не удалось настроить видео и звук', result, parent=window)

    def select():
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
        start_media_setup(data_dir, selected, results)
        window.after(75, poll)

    def clear():
        try:
            reset_media_directory(data_dir)
            refresh()
            status.set('Включён поиск в папке media и PATH. ' + RESTART_NOTICE)
        except MediaToolsError as error:
            messagebox.showerror('Не удалось сбросить настройки', str(error), parent=window)

    def close():
        if busy[0]:
            messagebox.showinfo('Идёт проверка', 'Дождись окончания проверки перед закрытием окна.', parent=window)
            return
        window.destroy()

    row = ttk.Frame(frame)
    row.pack(fill='x', pady=6)
    choose = ttk.Button(row, text='Выбрать папку…', command=select)
    choose.pack(side='left')
    reset = ttk.Button(row, text='Автоматический поиск', command=clear)
    reset.pack(side='left', padx=8)
    ttk.Button(row, text='Закрыть', command=close).pack(side='right')
    ttk.Button(frame, text='Официальный сайт FFmpeg',
               command=lambda: webbrowser.open('https://ffmpeg.org/download.html')).pack(anchor='w', pady=6)
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    return window
