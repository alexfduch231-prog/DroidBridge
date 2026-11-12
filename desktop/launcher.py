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
                import desktop.theme_settings
                import desktop.appearance_page
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
        Path(args.self_test).write_text(json.dumps({'ok': True, 'components_imported': ['server', 'viewer', 'pairing', 'apps', 'uploads', 'media', 'android_setup', 'appearance'], 'python': sys.version.split()[0],
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


class _SidebarViewport(ttk.Frame):
    """Keep native sidebar actions readable without reducing the selected font."""
    def __init__(self, parent):
        super().__init__(parent, style='DB.TFrame', width=220)
        from desktop.theme import palette_for_widget
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=1,
                                background=palette_for_widget(self)['background'])
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, style='DB.TFrame', padding=(12, 16))
        self.item = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.captions = {}
        self.labels = []
        self.pending = None
        self.canvas.bind('<Configure>', self._schedule)
        self.content.bind('<Configure>', self._schedule)
        self.bind('<Destroy>', self._dispose, add='+')
        owner = self.winfo_toplevel()
        self.bindings = [(event, owner.bind(event, callback, add='+')) for event, callback in (
            ('<Configure>', self._schedule), ('<FocusIn>', self._reveal),
            ('<MouseWheel>', self._wheel), ('<<DroidBridgeThemeChanged>>', self._schedule))]

    def _schedule(self, _event=None):
        if (_event is not None and _event.type == tk.EventType.Configure and
                _event.widget not in (self.master, self.canvas, self.content, self.winfo_toplevel())):
            return
        if self.pending is None:
            self.pending = self.after_idle(self._layout)

    def _layout(self):
        self.pending = None
        from desktop.theme import palette_for_widget
        self.canvas.configure(background=palette_for_widget(self)['background'])
        limit = max(220, int(self.master.winfo_width() * .45))
        style = ttk.Style(self)
        natural = 220
        measurements = []
        for button, caption in self.captions.items():
            name = button.cget('style') or 'TButton'
            # Measure the style's own Tcl font. Copying it through Font(font=)
            # can materialize stale point metrics after tk scaling changes.
            button_font = style.lookup(name, 'font')
            def measure(text, button_font=button_font):
                return int(self.tk.call('font', 'measure', button_font, text))
            padding = self.tk.splitlist(style.lookup(name, 'padding'))
            horizontal = int(padding[0]) * 2 if padding else 0
            if len(padding) >= 3:
                horizontal = int(padding[0]) + int(padding[2])
            # The image border has explicit zero padding; only style padding
            # and the compound icon consume the native text parcel.
            overhead = 4 + horizontal + (16 if button.cget('image') else 0)
            natural = max(natural, measure(caption) + overhead + 24)
            measurements.append((button, caption, measure, overhead))
        width = min(limit, natural)
        if int(self.cget('width')) != width:
            self.configure(width=width)
        available = max(1, self.canvas.winfo_width())
        for button, caption, measure, overhead in measurements:
            budget = max(1, available - 24 - overhead)
            lines, line = [], ''
            for word in caption.split():
                candidate = (line + ' ' + word).strip()
                if line and measure(candidate) > budget:
                    lines.append(line)
                    line = ''
                # A single long word must also fit at high DPI/minimum width.
                for char in word:
                    candidate = line + char
                    if line and measure(candidate) > budget:
                        lines.append(line)
                        line = char
                    else:
                        line = candidate
                line += ' '
            lines.append(line.rstrip())
            rendered = '\n'.join(part.rstrip() for part in lines)
            if str(button.cget('text')) != rendered:
                button.configure(text=rendered)
        for label in self.labels:
            label.configure(wraplength=max(1, available - 48))
        height = max(self.canvas.winfo_height(), self.content.winfo_reqheight())
        self.canvas.itemconfigure(self.item, width=available, height=height)
        self.canvas.configure(scrollregion=(0, 0, available, height))
        overflow = height > self.canvas.winfo_height()
        if overflow and not self.scrollbar.winfo_manager():
            self.scrollbar.pack(side='right', fill='y', before=self.canvas)
        elif not overflow and self.scrollbar.winfo_manager():
            self.scrollbar.pack_forget()
            self.canvas.yview_moveto(0)

    def _reveal(self, event):
        if event.widget not in self.captions:
            return
        button = event.widget
        top = button.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + button.winfo_height()
        height = max(1, self.content.winfo_height())
        if top < self.canvas.canvasy(0):
            self.canvas.yview_moveto(max(0, top - 4) / height)
        elif bottom > self.canvas.canvasy(self.canvas.winfo_height()):
            self.canvas.yview_moveto((bottom + 4 - self.canvas.winfo_height()) / height)

    def _wheel(self, event):
        if str(event.widget).startswith(str(self) + '.') and event.delta:
            self.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), 'units')

    def _dispose(self, event):
        if event.widget is not self:
            return
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        for sequence, identifier in self.bindings:
            self.winfo_toplevel().unbind(sequence, identifier)


def run_launcher(update_signal=None):
    """Own all pages, timers and children for the lifetime of the root."""
    from desktop.navigation import PageHost
    from desktop.theme import scrollable_card
    root = tk.Tk()
    root.title('DroidBridge')
    root.geometry('940x760')
    root.minsize(800, 600)
    data = data_directory()
    from desktop.theme import ThemeController
    theme_controller = ThemeController(root, data)
    from desktop.window_chrome import WindowChrome
    chrome = WindowChrome(root, lambda: close(), title='DroidBridge')
    root.window_chrome = chrome
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

    shell = ttk.Frame(root, style='DB.TFrame')
    shell.pack(fill='both', expand=True)
    sidebar_view = _SidebarViewport(shell)
    sidebar_view.pack(side='left', fill='y')
    sidebar = sidebar_view.content
    def sidebar_label(parent, text, style, **packing):
        label = ttk.Label(parent, text=text, style=style)
        label.pack(anchor='w', padx=12, **packing)
        sidebar_view.labels.append(label)
        return label
    sidebar_label(sidebar, 'DroidBridge', 'DB.Title.TLabel', pady=(0, 4))
    sidebar_label(sidebar, 'ПК и телефон, рядом', 'DB.Subtitle.TLabel', pady=(0, 22))
    from update_protocol import CURRENT_VERSION
    footer = ttk.Frame(sidebar, style='DB.TFrame')
    footer.pack(side='bottom', fill='x')
    sidebar_label(footer, 'DroidBridge ' + CURRENT_VERSION, 'DB.Subtitle.TLabel', pady=(12, 4))
    def check_updates():
        from update_manager import start_manual_check
        start_manual_check(root, data, update_signal)
    update_button = ttk.Button(footer, text='Проверить обновления', width=0, style='DB.Sidebar.TButton', command=check_updates)
    update_button.pack(fill='x')
    sidebar_view.captions[update_button] = 'Проверить обновления'
    ttk.Separator(shell, orient='vertical').pack(side='left', fill='y')
    workspace = ttk.Frame(shell, style='DB.TFrame')
    workspace.pack(side='left', fill='both', expand=True)
    header = ttk.Frame(workspace, style='DB.TFrame', padding=(20, 14))
    header.pack(fill='x')
    status_label = ttk.Label(header, textvariable=status, style='DB.Subtitle.TLabel', wraplength=480)
    status_label.pack(anchor='w', pady=(0, 8))
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

    ttk.Button(controls, text='Запустить сервер', style='DB.Sidebar.TButton', command=start_server).pack(side='left')
    ttk.Button(controls, text='Остановить', style='DB.Sidebar.TButton', command=stop_server).pack(side='left', padx=(8, 0))
    wol_status = tk.StringVar(root, value='Включение ПК по сети настраивается один раз перед первым сопряжением. Автопроверок при запуске нет.')
    root.wol_status = wol_status
    def resize_header(event):
        status_label.configure(wraplength=max(100, event.width - 40))
    header.bind('<Configure>', resize_header, add='+')
    ttk.Separator(workspace, orient='horizontal').pack(fill='x')

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
        ttk.Label(content, textvariable=wol_status, style='DB.Muted.TLabel', wraplength=400).pack(anchor='w', pady=(16, 0))
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
        from desktop.appearance_page import build_appearance_page
        return build_appearance_page(parent, data, theme_controller)

    def wol_page(parent):
        from wol_setup import build_wol_page
        return build_wol_page(parent, data)

    navigation = PageHost(workspace, {'connection': connection_page, 'screen': screen_page,
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
                button.configure(style='DB.Nav.Selected.TButton' if name == key else 'DB.Nav.TButton')
            return page
        except (ImportError, OSError, ValueError) as error:
            messagebox.showerror('Раздел недоступен', str(error), parent=root)
            return None
    # Small monochrome XBM line icons scale with Tk without an emoji font.
    icon_bits = {
        'connection': '0x00,0x00,0x1c,0x00,0x22,0x00,0x22,0x00,0x1c,0x00,0x08,0x00,0x38,0x00,0x40,0x00,0x40,0x00,0x38,0x00,0x08,0x00,0x00,0x00',
        'screen': '0x00,0x00,0x7e,0x00,0x42,0x00,0x42,0x00,0x42,0x00,0x42,0x00,0x42,0x00,0x7e,0x00,0x18,0x00,0x3c,0x00,0x00,0x00,0x00,0x00',
        'apps': '0x00,0x00,0x66,0x00,0x66,0x00,0x00,0x00,0x66,0x00,0x66,0x00,0x00,0x00,0x66,0x00,0x66,0x00,0x00,0x00,0x00,0x00,0x00,0x00',
        'uploads': '0x00,0x00,0x08,0x00,0x1c,0x00,0x2a,0x00,0x08,0x00,0x08,0x00,0x08,0x00,0x42,0x00,0x42,0x00,0x7e,0x00,0x00,0x00,0x00,0x00',
        'wol': '0x00,0x00,0x08,0x00,0x2a,0x00,0x49,0x00,0x49,0x00,0x41,0x00,0x41,0x00,0x22,0x00,0x1c,0x00,0x00,0x00,0x00,0x00,0x00,0x00',
        'settings': '0x00,0x00,0x08,0x00,0x7e,0x00,0x08,0x00,0x20,0x00,0x7e,0x00,0x20,0x00,0x04,0x00,0x7e,0x00,0x04,0x00,0x00,0x00,0x00,0x00',
    }
    nav_icons = {key: tk.BitmapImage(master=root, foreground=theme_controller.palette['text'],
                    data='#define icon_width 12\n#define icon_height 12\nstatic char icon_bits[] = {\n' + bits + '\n};')
                 for key, bits in icon_bits.items()}
    root._navigation_icons = nav_icons
    root.bind('<<DroidBridgeThemeChanged>>', lambda _event: [image.configure(foreground=theme_controller.palette['text']) for image in nav_icons.values()], add='+')
    for key, title in (('connection', 'Подключение'), ('screen', 'Экран телефона'),
                       ('apps', 'Программы'), ('uploads', 'Приём файлов'), ('wol', 'Включение ПК'), ('settings', 'Настройки')):
        button = ttk.Button(sidebar, text=title, image=nav_icons[key], compound='left', width=0, style='DB.Nav.TButton', command=lambda key=key: show_section(key))
        button.pack(fill='x', pady=(0, 2))
        buttons[key] = button
        sidebar_view.captions[button] = title
    sidebar_view._schedule()
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
        chrome.dispose()
        theme_controller.dispose()
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
