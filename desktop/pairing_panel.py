"""Local desktop pairing approval. No remotely reachable approval route."""
import ipaddress
import os
from pathlib import Path
import re
import secrets
import time

from pairing import PairingSession, PairingServer

_PRIVATE = tuple(ipaddress.IPv4Network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def eligible_adapters(adapters):
    return [adapter for adapter in adapters if any(ipaddress.IPv4Address(adapter.ip) in net for net in _PRIVATE)]


def load_pairing_key(data_dir):
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'token.txt'
    if path.is_symlink():
        raise ValueError('Unsafe token storage')
    try:
        key = path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = path.read_text(encoding='utf-8').strip()
        else:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(key + '\n')
    if not re.fullmatch(r'[A-Za-z0-9_-]{22,256}', key):
        raise ValueError('Existing key is invalid; it was not replaced')
    return key


class PairingController:
    def __init__(self, data_dir, http_port=8765, server_factory=PairingServer, clock=time.monotonic):
        self.data_dir, self.http_port = Path(data_dir), http_port
        self.server_factory, self.clock = server_factory, clock
        self.session = self.server = None
        self.link = ''

    def rotate(self, adapter):
        if adapter not in eligible_adapters([adapter]):
            raise ValueError('Select a private LAN adapter')
        self.close()
        key = load_pairing_key(self.data_dir)
        self.session = PairingSession(key, adapter.ip, adapter.mac, adapter.broadcast,
                                      self.http_port, clock=self.clock)
        server = self.server_factory(self.session, self.data_dir, bind=adapter.ip, port=8767)
        try:
            server.start()
            link = self.session.bootstrap_link(port=server.port, fingerprint=server.fingerprint)
        except BaseException:
            server.close()
            self.session.reject()
            raise
        self.server, self.link = server, link
        return link

    def snapshot(self):
        if self.session is None:
            return dict(state='idle', device_name='', confirm_code='', expires_in=0)
        view = self.session.snapshot()
        if view['state'] in ('expired', 'rejected', 'consumed'):
            if self.server is not None:
                self.server.close()
                self.server = None
            self.link = ''
        return view

    def approve(self):
        return self.session is not None and self.session.approve()

    def reject(self):
        if self.session is not None:
            self.session.reject()
        self.close()

    def close(self):
        if self.session is not None:
            self.session.reject()
        if self.server is not None:
            self.server.close()
            self.server = None
        self.link = ''


def show_pairing(parent, data_dir: Path, http_port=8765):
    """Open native approval window. Closing/expiry immediately disables bootstrap."""
    import tkinter as tk
    from tkinter import ttk
    import qrcode
    from PIL import ImageTk
    from lan_discovery import windows_adapters

    texts = {
        'ru': dict(title='Подключить телефон', adapter='Сетевой адаптер', generate='Создать новый QR',
                   copy='Скопировать ссылку', approve='Разрешить', reject='Отклонить',
                   idle='Выбери домашний сетевой адаптер и создай QR.',
                   open='Отсканируй QR камерой телефона и открой ссылку в приложении.',
                   pending='Сравни код на телефоне. Разрешай только своё устройство.',
                   approved='Разрешено. Ожидаем сохранения на телефоне.', consumed='Телефон подключён.',
                   expired='QR истёк. Создай новый.', rejected='Сопряжение отменено.',
                   error='Не удалось создать QR. Проверь адаптер, порт и доступ к локальным данным.',
                   warning='Камера должна уметь открывать QR-ссылки. Запасной путь: вставить ссылку в приложении.\nСопряжение защищено TLS; старые команды управления по HTTP — только для доверенной сети.'),
        'en': dict(title='Pair phone', adapter='Network adapter', generate='Create new QR',
                   copy='Copy pairing link', approve='Allow', reject='Reject',
                   idle='Choose your home network adapter and create a QR.',
                   open='Scan with your phone camera and open the link in the app.',
                   pending='Compare this code with the phone. Only allow your own device.',
                   approved='Approved. Waiting for the phone to save settings.', consumed='Phone paired.',
                   expired='QR expired. Create a new one.', rejected='Pairing cancelled.',
                   error='Cannot create QR. Check adapter, port and access to local data.',
                   warning='The camera must support QR links. Fallback: paste the pairing link in the app.\nTLS protects pairing; legacy HTTP commands require a trusted network.')}
    window = tk.Toplevel(parent)
    window.title('VzaimoPult')
    window.geometry('600x780')
    controller = PairingController(data_dir, http_port)
    adapters = eligible_adapters(windows_adapters())
    language = tk.StringVar(value='ru')
    copied = ['']
    closed = [False]
    pending_after = [None]
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Combobox(frame, textvariable=language, values=['ru', 'en'], state='readonly', width=6).pack(anchor='e')
    title = ttk.Label(frame, font=('Segoe UI', 18, 'bold'))
    title.pack(anchor='w', pady=(0, 12))
    adapter_label = ttk.Label(frame)
    adapter_label.pack(anchor='w')
    selection = ttk.Combobox(frame, values=[a.ip for a in adapters], state='readonly')
    selection.pack(fill='x', pady=6)
    if len(adapters) == 1:
        selection.current(0)
    # With multiple adapters, explicit choice is mandatory; never assume the first MAC.
    qr = ttk.Label(frame, anchor='center')
    qr.pack(fill='both', expand=True, pady=8)
    status = ttk.Label(frame, wraplength=555, justify='left')
    status.pack(fill='x', pady=8)
    code = ttk.Label(frame, font=('Consolas', 25, 'bold'), anchor='center')
    code.pack(fill='x', pady=5)
    name = ttk.Label(frame, wraplength=555)
    name.pack(fill='x')
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=8)
    approve = ttk.Button(buttons, command=controller.approve)
    approve.pack(side='left')
    reject = ttk.Button(buttons, command=controller.reject)
    reject.pack(side='left', padx=8)
    controls = ttk.Frame(frame)
    controls.pack(fill='x', pady=8)
    generate = ttk.Button(controls)
    generate.pack(side='left')
    copy = ttk.Button(controls)
    copy.pack(side='left', padx=8)
    warning = ttk.Label(frame, wraplength=555, justify='left')
    warning.pack(fill='x', pady=8)
    failure = [False]

    def clear_clipboard():
        if copied[0]:
            try:
                if window.clipboard_get() == copied[0]:
                    window.clipboard_clear()
            except tk.TclError:
                pass
            copied[0] = ''

    def create():
        clear_clipboard()
        index = selection.current()
        if index < 0:
            return
        qr.configure(image='')
        qr.image = None
        try:
            link = controller.rotate(adapters[index])
            image = qrcode.make(link, box_size=4, border=4).convert('RGB')
            # Keep QR modules unblurred, including the quiet zone.
            photo = ImageTk.PhotoImage(image, master=window)
            qr.configure(image=photo)
            qr.image = photo
            failure[0] = False
        except Exception:
            failure[0] = True
            controller.close()

    def copy_link():
        if controller.link:
            window.clipboard_clear()
            window.clipboard_append(controller.link)
            copied[0] = controller.link

    generate.configure(command=create)
    copy.configure(command=copy_link)

    def refresh():
        if closed[0]:
            return
        text = texts[language.get()]
        window.title('VzaimoPult — ' + text['title'])
        title.configure(text=text['title'])
        adapter_label.configure(text=text['adapter'])
        generate.configure(text=text['generate'])
        copy.configure(text=text['copy'], state='normal' if controller.link else 'disabled')
        approve.configure(text=text['approve'])
        reject.configure(text=text['reject'])
        warning.configure(text=text['warning'])
        view = controller.snapshot()
        state = view['state']
        status.configure(text=text['error'] if failure[0] else text[state] + (' (%ds)' % view['expires_in'] if state in ('open', 'pending', 'approved') else ''))
        code.configure(text=view['confirm_code'] if state == 'pending' else '')
        name.configure(text=view['device_name'] if state == 'pending' else '')
        approve.configure(state='normal' if state == 'pending' else 'disabled')
        reject.configure(state='normal' if state in ('open', 'pending', 'approved') else 'disabled')
        if state in ('expired', 'rejected', 'consumed'):
            clear_clipboard()
            qr.configure(image='')
            qr.image = None
        pending_after[0] = window.after(250, refresh)

    def cleanup():
        if closed[0]:
            return
        closed[0] = True
        if pending_after[0] is not None:
            try:
                window.after_cancel(pending_after[0])
            except tk.TclError:
                pass
        clear_clipboard()
        controller.close()

    def close():
        cleanup()
        window.destroy()

    # Parent shutdown also destroys child windows without WM_DELETE_WINDOW.
    window.bind('<Destroy>', lambda event: cleanup() if event.widget is window else None)
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    return window
