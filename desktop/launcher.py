"""Visible opt-in launcher with one window for connection and settings."""
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
from desktop.theme import apply_theme


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
                import wol_setup
                import desktop.navigation
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
    return run_launcher(update_signal)


def run_launcher(update_signal=None):
    """Own all pages, timers and children for the lifetime of the root."""
    from desktop.navigation import PageHost
    from desktop.theme import scrollable_card
    root = tk.Tk()
    root.title('DroidBridge')
    root.geometry('940x760')
    root.minsize(800, 600)
    apply_theme(root)
    data = data_directory()
    # Embedded components use the same persistent media/log context as children.
    import os
    os.environ['VZAIMOPULT_DATA_DIR'] = str(data)
    children = []
    server = [None]
    host = tk.StringVar(root, value='')
    status = tk.StringVar(root, value='Сервер ещё не запущен. Автозапуска нет.')
    tick_timer, update_timer, mirror_timer = [None], [None], [None]
    from desktop.mirror_handoff import GuiMirrorHandoff
    mirror_handoff = GuiMirrorHandoff(data)
    try:
        mirror_handoff.heartbeat()
    except OSError:
        pass  # An unavailable handoff must not prevent local controls.
    closing = [False]

    header = ttk.Frame(root, style='DB.TFrame', padding=(20, 12))
    header.pack(fill='x')
    ttk.Label(header, text='DroidBridge', style='DB.Title.TLabel').pack(anchor='w')
    status_label = ttk.Label(header, textvariable=status, style='DB.Subtitle.TLabel', wraplength=720)
    status_label.pack(anchor='w', pady=(4, 8))
    controls = ttk.Frame(header, style='DB.TFrame')
    controls.pack(fill='x')

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

    ttk.Button(controls, text='Запустить сервер', style='DB.Primary.TButton', command=start_server).pack(side='left')
    ttk.Button(controls, text='Остановить', style='DB.TButton', command=stop_server).pack(side='left', padx=(8, 0))
    wol_status = tk.StringVar(root, value='Включение ПК по сети настраивается один раз перед первым сопряжением. Автопроверок при запуске нет.')
    root.wol_status = wol_status
    wol_summary = ttk.Label(header, textvariable=wol_status, style='DB.Muted.TLabel', wraplength=720)
    wol_summary.pack(fill='x', pady=(8, 0))
    def resize_summary(event):
        wol_summary.configure(wraplength=max(100, event.width - 40))
    header.bind('<Configure>', resize_summary, add='+')
    shell = ttk.Frame(root, style='DB.TFrame')
    shell.pack(fill='both', expand=True, padx=(20, 12), pady=(0, 12))
    sidebar = ttk.Frame(shell, style='DB.TFrame')
    sidebar.pack(side='left', fill='y', padx=(0, 12))

    def setup_page(parent):
        from android_setup import build_android_setup_page
        navigation.builders['connection'] = connection_page
        return build_android_setup_page(parent, data, pairing)

    def open_setup():
        navigation.builders['connection'] = setup_page
        show_section('connection', refresh=True)

    def connection_page(parent):
        from android_setup import should_show_on_startup
        if should_show_on_startup(data):
            return setup_page(parent)
        page = ttk.Frame(parent, style='DB.TFrame')
        content = scrollable_card(page)
        ttk.Label(content, text='Подключение', style='DB.Heading.TLabel').pack(anchor='w')
        ttk.Label(content, text='Запусти сервер кнопкой сверху. Установка приложения открывается только по твоему запросу.',
                  style='DB.Muted.TLabel', wraplength=400).pack(anchor='w', pady=(8, 12))
        ttk.Button(content, text='Установить приложение Android', style='DB.TButton', command=open_setup).pack(anchor='w', pady=(0, 8))
        ttk.Button(content, text='Приложение уже установлено', style='DB.Primary.TButton', command=pairing).pack(anchor='w')
        return page

    def pairing():
        from desktop.wol_onboarding import build_onboarding_page, load_completion
        gate_page = [None]
        def continue_pairing():
            # Only the live gate can authorize this visit. Returning to connection
            # requires another explicit pairing action and fresh adapter validation.
            if (closing[0] or navigation.current_key != 'connection'
                    or navigation.pages.get('connection') is not gate_page[0] or not load_completion(data)):
                return
            from pairing_panel import build_pairing_page
            def build_pairing(parent):
                navigation.builders['connection'] = connection_page
                return build_pairing_page(parent, data, http_port=8765)
            navigation.builders['connection'] = build_pairing
            show_section('connection', refresh=True)
        def build_gate(parent):
            navigation.builders['connection'] = connection_page
            gate_page[0] = build_onboarding_page(parent, data, on_completed=continue_pairing)
            return gate_page[0]
        navigation.builders['connection'] = build_gate
        show_section('connection', refresh=True)

    root.connection_pairing = pairing

    def screen_page(parent):
        page = ttk.Frame(parent, style='DB.TFrame')
        content = scrollable_card(page)
        ttk.Label(content, text='Экран телефона на ПК', style='DB.Heading.TLabel').pack(anchor='w')
        ttk.Label(content, text='Включи трансляцию в приложении и введи IP телефона.',
                  style='DB.Muted.TLabel', wraplength=400).pack(anchor='w', pady=(8, 12))
        ttk.Label(content, text='IP-адрес телефона', style='DB.TLabel').pack(anchor='w')
        entry = ttk.Entry(content, textvariable=host)
        entry.pack(fill='x', pady=(4, 12))
        active_viewer = [None]
        active_endpoint = [None]
        def matches_viewer(address, port):
            current = active_viewer[0]
            return (active_endpoint[0] == (address, port) and current is not None
                    and current.winfo_exists() and not current.viewer.stop.is_set())
        page.matches_viewer = matches_viewer
        def dispose_viewer():
            current, active_viewer[0] = active_viewer[0], None
            active_endpoint[0] = None
            if current is not None:
                current.dispose()
                if current.winfo_exists():
                    current.destroy()
        page.dispose = dispose_viewer
        def viewer(port=8768, *, auto_control=False):
            try:
                from runtime import load_component
                address = phone_address(host.get())
                if not (data / 'token.txt').is_file():
                    raise ValueError('Сначала запусти сервер и выполни сопряжение.')
                component = load_component('viewer')
                token = component.read_token(str(data / 'token.txt'))
                if not token:
                    raise ValueError('Ключ подключения пуст. Выполни сопряжение заново.')
                dispose_viewer()
                active_viewer[0] = component.build_viewer_page(
                    page, address, port, token, auto_control=auto_control)
                active_endpoint[0] = (address, port)
                content.master.master.destroy()  # Remove the setup viewport, not this page.
                active_viewer[0].pack(fill='both', expand=True)
            except (ImportError, OSError, ValueError) as error:
                messagebox.showerror('Не удалось открыть экран', str(error), parent=root)
        page.start_viewer = viewer
        ttk.Button(content, text='Открыть экран телефона', style='DB.Primary.TButton', command=viewer).pack(anchor='w')
        ttk.Label(content, text='Трансляция появится здесь. Чтобы отключиться, перейди в другой раздел.',
                  style='DB.Muted.TLabel', wraplength=400).pack(anchor='w', pady=(12, 0))
        return page

    def applications_page(parent):
        from apps_panel import build_apps_page
        return build_apps_page(parent, data)

    def uploads_page(parent):
        from upload_panel import build_uploads_page
        return build_uploads_page(parent, data)

    def settings_page(parent):
        from media_setup import build_media_page
        return build_media_page(parent, data)

    def wol_page(parent):
        from wol_setup import build_wol_page
        return build_wol_page(parent, data)

    navigation = PageHost(shell, {'connection': connection_page, 'screen': screen_page,
                                  'apps': applications_page, 'uploads': uploads_page,
                                  'settings': settings_page, 'wol': wol_page})
    navigation.pack(side='left', fill='both', expand=True)
    root.navigation = navigation
    buttons = {}
    def show_section(key, *, refresh=False):
        try:
            # Pairing is temporary: leaving connection closes its TLS session;
            # returning shows the explicit setup / already-installed choices.
            if key != 'connection':
                navigation.builders['connection'] = connection_page
            page = navigation.show_page(key, refresh=refresh)
            for name, button in buttons.items():
                button.configure(style='DB.Primary.TButton' if name == key else 'DB.TButton')
            return page
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Раздел недоступен', str(error), parent=root)
            return None
    for key, title in (('connection', 'Подключение'), ('screen', 'Экран телефона'),
                       ('apps', 'Программы'), ('uploads', 'Приём файлов'), ('wol', 'Включение ПК'), ('settings', 'Настройки')):
        button = ttk.Button(sidebar, text=title, style='DB.TButton', command=lambda key=key: show_section(key))
        button.pack(fill='x', pady=(0, 4))
        buttons[key] = button
    # Direct navigation is also used by integration tests and explicit page actions.
    root.show_section = show_section
    show_section('connection')

    def tick():
        if server[0] is not None:
            code = server[0].poll()
            status.set('Процесс сервера запущен. Доступность сети не проверялась.' if code is None
                       else 'Сервер завершён (код %s). См. listener.log в папке данных.' % code)
        tick_timer[0] = root.after(1000, tick)

    def cleanup(event):
        if event.widget is not root or closing[0]:
            return
        closing[0] = True
        try:
            mirror_handoff.close()
        except OSError:
            pass
        for timer in (tick_timer, update_timer, mirror_timer):
            if timer[0] is not None:
                root.after_cancel(timer[0])
                timer[0] = None
        try:
            navigation.dispose()
        finally:
            # Update shutdown asks components to drain via the shared event.
            if update_signal is None or not update_signal.is_set():
                for child in children:
                    if child.poll() is None:
                        child.terminate()

    root.bind('<Destroy>', cleanup, add='+')
    def close():
        live = [child for child in children if child.poll() is None]
        if live and not messagebox.askyesno('Закрыть DroidBridge?', 'Остановить запущенные этим окном сервер и просмотр?', parent=root):
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    tick_timer[0] = root.after(1000, tick)
    from update_manager import start_startup_check
    start_startup_check(root, data, update_signal)
    def poll_update_shutdown():
        if update_signal is not None and update_signal.is_set():
            try:
                navigation.dispose()
            finally:
                root.destroy()
            return
        update_timer[0] = root.after(200, poll_update_shutdown)
    update_timer[0] = root.after(200, poll_update_shutdown)
    def poll_mirror_requests():
        if mirror_timer[0] is not None:
            root.after_cancel(mirror_timer[0])
            mirror_timer[0] = None
        try:
            mirror_handoff.heartbeat()
            request = mirror_handoff.consume()
            if request is not None:
                address = phone_address(request.host)
                port = int(request.port)
                if not 1 <= port <= 65535:
                    raise ValueError('Invalid viewer port')
                host.set(address)
                current = navigation.pages.get('screen')
                # Android retries a handoff when its HTTP response was lost.
                # Never tear down the matching connection (even before hello),
                # nor override a user's control opt-out on an existing viewer.
                if (navigation.current_key == 'screen' and current is not None
                        and current.matches_viewer(address, port)):
                    return
                page = show_section('screen', refresh=True)
                if page is not None:
                    page.start_viewer(port=port, auto_control=True)
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # Ignore stale/unreadable handoffs; the next poll can recover.
        finally:
            if not closing[0]:
                mirror_timer[0] = root.after(250, poll_mirror_requests)
    mirror_timer[0] = root.after(250, poll_mirror_requests)
    root.poll_mirror_requests = poll_mirror_requests
    try:
        root.mainloop()
    finally:
        if update_signal is not None:
            update_signal.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
