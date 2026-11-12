"""Visible opt-in launcher: control, temporary pairing, viewer start on explicit actions."""
import argparse
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)

# PyInstaller analysis needs these imports; they do not start any service.
import tkinter as tk
from tkinter import ttk, messagebox
from runtime import data_directory, phone_address, run_component, start_child


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--component', choices=['server', 'viewer'])
    parser.add_argument('--self-test', metavar='OUTPUT_JSON')
    args, remaining = parser.parse_known_args()
    if args.self_test:
        import json
        from PIL import Image, ImageTk, ImageGrab
        import ssl
        import ctypes
        import os
        import tempfile
        from runtime import load_component
        # Import entrypoints only, never call main or bind sockets. Modules create DATA_DIR
        # at import, so isolate it and restore the caller's environment afterwards.
        previous_data = os.environ.get('VZAIMOPULT_DATA_DIR')
        try:
            with tempfile.TemporaryDirectory(prefix='vzaimopult-selftest-') as isolated:
                os.environ['VZAIMOPULT_DATA_DIR'] = isolated
                load_component('server')
                load_component('viewer')
                import pairing
                import app_catalog
                import pairing_panel
                import apps_panel
                import upload_settings
                import upload_panel
                import media_tools
                import media_setup
                import android_setup
                import update_protocol
                import update_manager
                import update_helper
                import qrcode
                test_root = tk.Tk()
                test_root.withdraw()
                try:
                    qr = qrcode.make('vzaimopult-selftest-not-a-pairing-ticket')
                    image = ImageTk.PhotoImage(qr.get_image(), master=test_root)
                    if image.width() < 1:
                        raise RuntimeError('QR/Tk image creation failed')
                    test_root.update_idletasks()
                finally:
                    test_root.destroy()
        finally:
            if previous_data is None:
                os.environ.pop('VZAIMOPULT_DATA_DIR', None)
            else:
                os.environ['VZAIMOPULT_DATA_DIR'] = previous_data
        Path(args.self_test).write_text(json.dumps({'ok': True, 'components_imported': ['server', 'viewer', 'pairing', 'apps', 'uploads', 'media', 'android_setup'], 'python': sys.version.split()[0],
            'pillow': Image.__version__, 'tls': ssl.OPENSSL_VERSION,
            'frozen': bool(getattr(sys, 'frozen', False))}), encoding='utf-8')
        return 0
    if args.component:
        return run_component(args.component, remaining)
    if remaining:
        parser.error('Unexpected arguments')
    from runtime import create_update_signal
    update_signal = create_update_signal()
    if update_signal is not None and update_signal.is_set():
        update_signal.close()
        return 0
    root = tk.Tk()
    root.title('DroidBridge')
    root.geometry('640x740')
    root.minsize(640, 740)
    root.configure(bg='#f4f6fa')
    style = ttk.Style(root)
    style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
    style.configure('TLabel', font=('Segoe UI', 10))
    style.configure('TButton', font=('Segoe UI', 10), padding=(10, 7))
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='DroidBridge', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Твой ПК и телефон — в одной локальной сети.').pack(anchor='w', pady=(2, 18))
    status = tk.StringVar(value='Сервер ещё не запущен. Автозапуска нет.')
    ttk.Label(frame, textvariable=status, wraplength=490).pack(anchor='w', pady=(0, 10))
    children = []
    server = [None]
    def start_server():
        if server[0] is not None and server[0].poll() is None:
            return
        try:
            server[0] = start_child('server')
            children.append(server[0])
            status.set('Запуск сервера…')
        except OSError as error:
            messagebox.showerror('Не удалось запустить сервер', str(error), parent=root)
    def stop_server():
        if server[0] is not None and server[0].poll() is None:
            server[0].terminate()
            status.set('Остановка сервера…')
    row = ttk.Frame(frame)
    row.pack(fill='x')
    ttk.Button(row, text='Запустить сервер', command=start_server).pack(side='left')
    ttk.Button(row, text='Остановить', command=stop_server).pack(side='left', padx=8)
    def pairing():
        try:
            from pairing_panel import show_pairing
            show_pairing(root, data_directory(), http_port=8765)
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Сопряжение недоступно', str(error), parent=root)
    from android_setup import should_show_on_startup, show_android_setup
    def android_setup():
        show_android_setup(root, data_directory(), pairing)
    ttk.Button(frame, text='Приложение на телефон / подключить', command=android_setup).pack(anchor='w', pady=8)
    ttk.Label(frame, text='Сопряжение доступно сразу; для управления запусти сервер.', wraplength=540).pack(anchor='w')
    def applications():
        try:
            from apps_panel import show_apps
            show_apps(root, data_directory())
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Программы недоступны', str(error), parent=root)
    ttk.Button(frame, text='Программы / Applications', command=applications).pack(anchor='w')
    def uploads():
        try:
            from upload_panel import show_uploads
            show_uploads(root, data_directory())
        except (ImportError, OSError, ValueError):
            messagebox.showerror('Приём файлов недоступен',
                                 'Проверь локальную папку и настройки приёма файлов.', parent=root)
    ttk.Button(frame, text='Приём файлов / Received files', command=uploads).pack(anchor='w', pady=8)
    def media_settings():
        from media_setup import show_media_setup
        show_media_setup(root, data_directory())
    ttk.Button(frame, text='Настроить видео и звук', command=media_settings).pack(anchor='w', pady=8)
    from listener.media_tools import MediaToolsError, resolve_media_tools
    try:
        media_tools = resolve_media_tools(data_directory())
        media_available = bool(media_tools.ffmpeg and media_tools.ffplay)
    except MediaToolsError:
        media_available = False
    ttk.Label(frame, text=('Видео и звук готовы. Дополнительная установка не нужна.' if media_available
              else 'Инструменты видео и звука не найдены. Открой настройку.'), wraplength=540).pack(anchor='w')
    ttk.Separator(frame).pack(fill='x', pady=8)
    ttk.Label(frame, text='Экран телефона на ПК', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=6)
    ttk.Label(frame, text='Включи трансляцию в приложении и введи IP телефона.').pack(anchor='w')
    host = ttk.Entry(frame, font=('Segoe UI', 12))
    host.pack(fill='x', pady=8)
    def viewer():
        try:
            address = phone_address(host.get())
            if not (data_directory() / 'token.txt').is_file():
                raise ValueError('Сначала запусти сервер и выполни сопряжение.')
            children.append(start_child('viewer', '--connect', address))
        except (OSError, ValueError) as error:
            messagebox.showerror('Не удалось открыть экран', str(error), parent=root)
    ttk.Button(frame, text='Открыть экран телефона', command=viewer).pack(anchor='w')
    ttk.Label(frame, text='Данные и ключи хранятся только в профиле Windows.\nНе открывай порты роутера в интернет.', wraplength=490).pack(anchor='w', pady=(16, 0))
    tick_timer = [None]
    def tick():
        if server[0] is not None:
            code = server[0].poll()
            status.set('Процесс сервера запущен. Доступность сети не проверялась.' if code is None
                       else 'Сервер завершён (код %s). См. listener.log в папке данных.' % code)
        tick_timer[0] = root.after(1000, tick)
    def close():
        live = [child for child in children if child.poll() is None]
        if live and not messagebox.askyesno('Закрыть DroidBridge?', 'Остановить запущенные этим окном сервер и просмотр?', parent=root):
            return
        for child in live:
            child.terminate()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    tick_timer[0] = root.after(1000, tick)
    if should_show_on_startup(data_directory()):
        pending_setup = root.after(0, android_setup)
        def cancel_pending_setup(event):
            if event.widget is root:
                root.after_cancel(pending_setup)
        root.bind('<Destroy>', cancel_pending_setup, add='+')
    from update_manager import start_startup_check
    start_startup_check(root, data_directory(), update_signal)
    update_timer = [None]
    def cancel_update_timer(event):
        if event.widget is root:
            if update_timer[0] is not None:
                root.after_cancel(update_timer[0])
                update_timer[0] = None
            if tick_timer[0] is not None:
                root.after_cancel(tick_timer[0])
                tick_timer[0] = None
    root.bind('<Destroy>', cancel_update_timer, add='+')
    def poll_update_shutdown():
        if update_signal is not None and update_signal.is_set():
            # Every same-path GUI/component observes the event. No terminate here:
            # server handlers drain, viewer closes its owned decoders normally.
            root.destroy()
            return
        update_timer[0] = root.after(200, poll_update_shutdown)
    update_timer[0] = root.after(200, poll_update_shutdown)
    try:
        root.mainloop()
    finally:
        if update_signal is not None:
            update_signal.close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
