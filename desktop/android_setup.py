"""Optional local Android setup. Importing this module never opens Tk or the network."""
import json
import os
from pathlib import Path
import tempfile

APK_DOWNLOAD_URL = 'https://github.com/alexfduch231-prog/DroidBridge/releases/download/v1.0.2/DroidBridge-1.14-android.apk'
_CONFIG_LIMIT = 4096


def should_show_on_startup(data_dir):
    """Only a valid explicit opt-out suppresses onboarding; reads are bounded."""
    path = Path(data_dir) / 'android_setup.json'
    try:
        if path.is_symlink():
            return True
        with path.open('rb') as stream:
            raw = stream.read(_CONFIG_LIMIT + 1)
        if len(raw) > _CONFIG_LIMIT:
            return True
        config = json.loads(raw.decode('utf-8'))
        return not (isinstance(config, dict) and type(config.get('version')) is int
                    and config['version'] == 1 and config.get('dont_show') is True)
    except (OSError, ValueError, RecursionError):
        return True


def save_dont_show(data_dir, dont_show):
    """Atomically replace only this feature's tiny preference file."""
    if type(dont_show) is not bool:
        raise ValueError('Expected a boolean preference')
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'android_setup.json'
    if destination.is_symlink():
        raise OSError('Unsafe Android setup preference storage')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.android-setup-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': 1, 'dont_show': dont_show}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def show_android_setup(parent, data_dir, on_pair):
    """Show one non-modal window; pairing runs only after its explicit button."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    existing = getattr(parent, '_android_setup_window', None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        return existing
    window = tk.Toplevel(parent)
    parent._android_setup_window = window
    window.title('DroidBridge — приложение на телефон')
    window.geometry('640x700')
    window.minsize(640, 700)
    window.transient(parent)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='DroidBridge на Android', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Сначала установи приложение на телефон, затем подключи его к ПК. '
              'Скачивание APK и безопасное сопряжение — разные шаги.',
              wraplength=590).pack(anchor='w', pady=10)
    content = ttk.Frame(frame)
    content.pack(fill='both', expand=True)
    dont_show = tk.BooleanVar(master=window, value=not should_show_on_startup(data_dir))

    def remember():
        try:
            save_dont_show(data_dir, dont_show.get())
        except (OSError, ValueError):
            dont_show.set(not should_show_on_startup(data_dir))
            messagebox.showerror('Настройка не сохранена',
                                 'Не удалось сохранить выбор в локальной папке данных.', parent=window)

    ttk.Checkbutton(frame, text='Больше не показывать при запуске', variable=dont_show,
                    command=remember).pack(anchor='w', pady=(12, 0))

    def close():
        window.destroy()

    def pair():
        close()
        on_pair()

    def install():
        import qrcode
        from PIL import ImageTk
        for child in content.winfo_children():
            child.destroy()
        ttk.Label(content, text='QR для скачивания APK — не QR сопряжения',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 6))
        qr_label = ttk.Label(content, anchor='center')
        qr_label.pack(fill='x')
        try:
            image = qrcode.make(APK_DOWNLOAD_URL, box_size=4, border=4).convert('RGB')
            qr_label.image = ImageTk.PhotoImage(image, master=window)
            qr_label.configure(image=qr_label.image)
        except (OSError, ValueError, tk.TclError):
            qr_label.configure(text='QR недоступен. Скопируй публичную ссылку ниже.')
        ttk.Label(content, text='1. Отсканируй QR обычной камерой телефона и скачай APK из GitHub.\n'
                  '2. Открой APK на Android. При запросе разреши установку из неизвестных '
                  'источников только выбранному браузеру или файловому менеджеру.\n'
                  '3. Подтверди установку вручную. После установки разрешение можно отключить.\n'
                  'ПК ничего не устанавливает автоматически. Этот публичный QR не содержит '
                  'ключей и не подключает телефон к ПК.',
                  wraplength=590, justify='left').pack(anchor='w', pady=8)
        link = ttk.Entry(content)
        link.insert(0, APK_DOWNLOAD_URL)
        link.configure(state='readonly')
        link.pack(fill='x')
        row = ttk.Frame(content)
        row.pack(fill='x', pady=6)

        def copy():
            window.clipboard_clear()
            window.clipboard_append(APK_DOWNLOAD_URL)

        def open_link():
            import webbrowser
            webbrowser.open(APK_DOWNLOAD_URL)

        ttk.Button(row, text='Скопировать ссылку APK', command=copy).pack(side='left')
        ttk.Button(row, text='Открыть ссылку APK', command=open_link).pack(side='left', padx=8)
        ttk.Button(content, text='Установлено → подключить к ПК', command=pair).pack(anchor='w', pady=6)

    ttk.Button(content, text='Установить на телефон', command=install).pack(anchor='w', pady=8)
    ttk.Button(content, text='Уже установлено → подключить к ПК', command=pair).pack(anchor='w', pady=8)
    ttk.Label(content, text='При подключении откроется отдельное окно для создания временного QR '
              'сопряжения. Просто закрыть это окно — ничего не запускать.',
              wraplength=590).pack(anchor='w', pady=10)
    window.protocol('WM_DELETE_WINDOW', close)
    return window
