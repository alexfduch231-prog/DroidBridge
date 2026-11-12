"""Local-only upload folder picker. Importing creates no windows or services."""
import locale
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)
from listener.upload_settings import (UploadSettingsError, upload_directory,
                                      save_upload_directory, reset_upload_directory)


class LocalUploadsModel:
    """PC-local settings; the source guard is not network authentication."""
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    @property
    def directory(self) -> Path:
        return upload_directory(self.data_dir)

    @staticmethod
    def _local(source):
        if source != 'local':
            raise PermissionError('Upload settings are available only on this PC.')

    def select_from_picker(self, selected_path, *, source='local'):
        self._local(source)
        if selected_path:
            save_upload_directory(self.data_dir, selected_path)

    def reset(self, *, source='local'):
        self._local(source)
        reset_upload_directory(self.data_dir)


_LABELS = {
    'en': {'title': 'Received files', 'intro': 'Folder for files received from your phone',
           'local': 'Choose a folder only on this PC. Changes apply to the next upload.',
           'choose': 'Choose folder…', 'reset': 'Reset to Downloads', 'close': 'Close',
           'pick': 'Choose an existing folder on this PC', 'unavailable': 'Folder unavailable — choose another or reset.',
           'error': 'Could not update upload folder',
           'error_body': 'Check the selected folder and local settings, then try again.'},
    'ru': {'title': 'Приём файлов', 'intro': 'Папка для файлов, полученных с телефона',
           'local': 'Выбор папки — только на этом ПК. Изменения действуют со следующей загрузки.',
           'choose': 'Выбрать папку…', 'reset': 'Сбросить в «Загрузки»', 'close': 'Закрыть',
           'pick': 'Выбери существующую папку на этом ПК', 'unavailable': 'Папка недоступна — выбери другую или сбрось.',
           'error': 'Не удалось изменить папку приёма',
           'error_body': 'Проверь выбранную папку и локальные настройки, затем повтори.'},
}


def build_uploads_page(parent, data_dir):
    """Build an unpacked upload settings frame, without creating a window."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    model = LocalUploadsModel(data_dir)
    try:
        language = 'ru' if (locale.getlocale()[0] or '').lower().startswith('ru') else 'en'
    except (ValueError, TypeError):
        language = 'en'
    words = _LABELS[language]
    try:
        from theme import scrollable_card
    except ModuleNotFoundError:
        from desktop.theme import scrollable_card
    window = ttk.Frame(parent, style='DB.TFrame')
    window.dispose = lambda: window.destroy() if window.winfo_exists() else None
    frame = scrollable_card(window)
    ttk.Label(frame, style='DB.Heading.TLabel', text=words['intro'], wraplength=580).pack(anchor='w')
    current = tk.StringVar(master=window)
    # Horizontal scrolling keeps long local paths accessible without clipping the window.
    entry = ttk.Entry(frame, textvariable=current, state='readonly')
    entry.pack(fill='x', pady=(12, 0))
    scroll = ttk.Scrollbar(frame, orient='horizontal', command=entry.xview)
    entry.configure(xscrollcommand=scroll.set)
    scroll.pack(fill='x', pady=(0, 10))

    def refresh():
        try:
            current.set(str(model.directory))
        except (UploadSettingsError, OSError, ValueError):
            current.set(words['unavailable'])

    def guarded(action):
        try:
            action()
            refresh()
        except (UploadSettingsError, OSError, ValueError):
            # OS exceptions may include private paths; never display their text.
            messagebox.showerror(words['error'], words['error_body'], parent=window)

    def select():
        try:
            initial = str(model.directory)
        except (UploadSettingsError, OSError, ValueError):
            initial = str(Path.home())
        selected = filedialog.askdirectory(parent=window, title=words['pick'],
                                           initialdir=initial, mustexist=True)
        if selected:
            guarded(lambda: model.select_from_picker(selected))

    row = ttk.Frame(frame, style='DB.Card.TFrame')
    row.pack(fill='x', pady=(0, 12))
    ttk.Button(row, style='DB.Primary.TButton', text=words['choose'], command=select).pack(side='left')
    ttk.Button(row, text=words['reset'], command=lambda: guarded(model.reset)).pack(side='left', padx=8)
    ttk.Label(frame, style='DB.Muted.TLabel', text=words['local'], wraplength=580).pack(anchor='w')
    refresh()
    window.close_container = row
    window.title_text = words['title']
    window.close_text = words['close']
    return window


def show_uploads(parent, data_dir):
    """Compatibility wrapper around the embedded upload settings page."""
    import tkinter as tk
    from tkinter import ttk
    try:
        from theme import apply_theme
    except ModuleNotFoundError:
        from desktop.theme import apply_theme

    window = tk.Toplevel(parent)
    try:
        apply_theme(window)
        page = build_uploads_page(window, data_dir)
        window.title(page.title_text)
        window.geometry(f'700x{min(290, max(400, window.winfo_screenheight() - 100))}')
        window.minsize(520, 400)
        window.transient(parent)
        page.pack(fill='both', expand=True)
        ttk.Button(page.close_container, text=page.close_text, command=window.destroy).pack(side='right')
    except Exception:
        window.destroy()
        raise
    return window
