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
from desktop.theme import PALETTE, apply_theme, card


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
                apply_theme(test_root)
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
    root.geometry('940x760')
    root.minsize(800, 600)
    apply_theme(root)
    header = ttk.Frame(root, style='DB.TFrame', padding=(28, 20, 28, 16))
    header.pack(fill='x')
    accent = ttk.Frame(header, style='DB.Accent.TFrame', width=5)
    accent.pack(side='left', fill='y', padx=(0, 16))
    brand = ttk.Frame(header, style='DB.TFrame')
    brand.pack(side='left', fill='x', expand=True)
    ttk.Label(brand, text='DroidBridge', style='DB.Title.TLabel').pack(anchor='w')
    ttk.Label(brand, text='Твой ПК и телефон — в одной локальной сети.',
              style='DB.Subtitle.TLabel').pack(anchor='w', pady=(4, 0))
    shell = ttk.Frame(root, style='DB.TFrame')
    shell.pack(fill='both', expand=True, padx=(28, 12), pady=(0, 16))
    canvas = tk.Canvas(shell, background=PALETTE['background'], highlightthickness=0,
                       borderwidth=0, takefocus=False)
    scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
    scrollbar.pack(side='right', fill='y', padx=(8, 0))
    canvas.pack(side='left', fill='both', expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    frame = ttk.Frame(canvas, style='DB.TFrame')
    content_id = canvas.create_window((0, 0), window=frame, anchor='nw')
    wrapped = []
    def resize_content(event):
        canvas.itemconfigure(content_id, width=event.width)
        for label in wrapped:
            label.configure(wraplength=max(200, event.width - 40))
    canvas.bind('<Configure>', resize_content)
    frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    def scroll_wheel(event):
        if event.num == 4:
            units = -1
        elif event.num == 5:
            units = 1
        else:
            units = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        if canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(units, 'units')
    # Root bindings receive events from owned descendants, without bind_all leaks
    # or hijacking wheel events in the separate tool windows.
    def wheel_in_main(event):
        if event.widget.winfo_toplevel() is root:
            scroll_wheel(event)
    root.bind('<MouseWheel>', wheel_in_main, add='+')
    root.bind('<Button-4>', wheel_in_main, add='+')
    root.bind('<Button-5>', wheel_in_main, add='+')
    def reveal_focus(event):
        widget = event.widget
        if widget.winfo_toplevel() is root and widget is not root:
            top = widget.winfo_rooty() - frame.winfo_rooty()
            bottom = top + widget.winfo_height()
            visible_top = canvas.canvasy(0)
            height = canvas.winfo_height()
            if top < visible_top or bottom > visible_top + height:
                total = max(1, frame.winfo_height())
                canvas.yview_moveto(max(0, top - 16) / total)
    frame.bind('<FocusIn>', reveal_focus, add='+')
    root.bind('<FocusIn>', reveal_focus, add='+')
    def body_label(parent, text=None, **kwargs):
        label = ttk.Label(parent, text=text, style='DB.Muted.TLabel', wraplength=780, **kwargs)
        wrapped.append(label)
        return label
    connection = card(frame)
    connection.pack(fill='x', pady=(0, 12))
    ttk.Label(connection, text='Подключение', style='DB.Heading.TLabel').pack(anchor='w')
    status = tk.StringVar(value='Сервер ещё не запущен. Автозапуска нет.')
    body_label(connection, textvariable=status).pack(anchor='w', pady=(8, 12))
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
    row = ttk.Frame(connection, style='DB.Card.TFrame')
    row.pack(fill='x')
    ttk.Button(row, text='Запустить сервер', style='DB.Primary.TButton', command=start_server).pack(side='left')
    ttk.Button(row, text='Остановить', style='DB.TButton', command=stop_server).pack(side='left', padx=8)
    def pairing():
        try:
            from pairing_panel import show_pairing
            show_pairing(root, data_directory(), http_port=8765)
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Сопряжение недоступно', str(error), parent=root)
    from android_setup import should_show_on_startup, show_android_setup
    def android_setup():
        show_android_setup(root, data_directory(), pairing)
    ttk.Button(connection, text='Приложение на телефон / подключить', style='DB.TButton', command=android_setup).pack(anchor='w', pady=(12, 8))
    body_label(connection, 'Сопряжение доступно сразу; для управления запусти сервер.').pack(anchor='w')
    def applications():
        try:
            from apps_panel import show_apps
            show_apps(root, data_directory())
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Программы недоступны', str(error), parent=root)
    def uploads():
        try:
            from upload_panel import show_uploads
            show_uploads(root, data_directory())
        except (ImportError, OSError, ValueError):
            messagebox.showerror('Приём файлов недоступен',
                                 'Проверь локальную папку и настройки приёма файлов.', parent=root)
    def media_settings():
        from media_setup import show_media_setup
        show_media_setup(root, data_directory())
    from listener.media_tools import MediaToolsError, resolve_media_tools
    try:
        media_tools = resolve_media_tools(data_directory())
        media_available = bool(media_tools.ffmpeg and media_tools.ffplay)
    except MediaToolsError:
        media_available = False
    screen = card(frame)
    screen.pack(fill='x', pady=(0, 12))
    ttk.Label(screen, text='Экран телефона на ПК', style='DB.Heading.TLabel').pack(anchor='w')
    body_label(screen, 'Включи трансляцию в приложении и введи IP телефона.').pack(anchor='w', pady=(8, 12))
    ttk.Label(screen, text='IP-адрес телефона', style='DB.TLabel').pack(anchor='w')
    host = ttk.Entry(screen)
    host.pack(fill='x', pady=(4, 12))
    def viewer():
        try:
            address = phone_address(host.get())
            if not (data_directory() / 'token.txt').is_file():
                raise ValueError('Сначала запусти сервер и выполни сопряжение.')
            children.append(start_child('viewer', '--connect', address))
        except (OSError, ValueError) as error:
            messagebox.showerror('Не удалось открыть экран', str(error), parent=root)
    ttk.Button(screen, text='Открыть экран телефона', style='DB.TButton', command=viewer).pack(anchor='w')
    tools = card(frame)
    tools.pack(fill='x', pady=(0, 12))
    ttk.Label(tools, text='Инструменты', style='DB.Heading.TLabel').pack(anchor='w')
    actions = ttk.Frame(tools, style='DB.Card.TFrame')
    actions.pack(fill='x', pady=(12, 0))
    ttk.Button(actions, text='Программы / Applications', style='DB.TButton', command=applications).pack(side='left')
    ttk.Button(actions, text='Приём файлов / Received files', style='DB.TButton', command=uploads).pack(side='left', padx=(8, 0))
    ttk.Button(tools, text='Настроить видео и звук', style='DB.TButton', command=media_settings).pack(anchor='w', pady=(12, 8))
    body_label(tools, ('Видео и звук готовы. Дополнительная установка не нужна.' if media_available
              else 'Инструменты видео и звука не найдены. Открой настройку.')).pack(anchor='w')
    ttk.Label(frame, text='Данные и ключи хранятся только в профиле Windows.\nНе открывай порты роутера в интернет.', style='DB.Subtitle.TLabel', wraplength=700).pack(anchor='w', pady=(4, 8))
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
