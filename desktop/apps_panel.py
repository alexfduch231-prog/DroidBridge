"""Local-only Tk application editor; importing this module creates no windows.

The phone can select catalog IDs, never paths. Do not wire this model to HTTP
mutation endpoints. The file picker is the only UI that supplies launch paths.
"""
import copy
import locale
from pathlib import Path
import sys
import uuid

# Running desktop/launcher.py directly puts desktop/, not the repository, on sys.path.
if not getattr(sys, 'frozen', False):
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)
from listener.app_catalog import (CatalogError, SUPPORTED_EXTENSIONS, load_catalog,
                                  save_catalog, validate_catalog)


class LocalAppsModel:
    """Headless editor. 'source' is a guard against accidental remote reuse,
    not authentication; this object must never be exposed as a network API.
    """
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / 'apps.json'
        self._catalog = load_catalog(self.path)

    @property
    def apps(self):
        return copy.deepcopy(self._catalog['apps'])

    @staticmethod
    def _local(source):
        if source != 'local':
            raise PermissionError('Application editing is only available on this PC.')

    def _commit(self, value):
        # Avoid silently destroying edits from a second local editor.
        if load_catalog(self.path) != self._catalog:
            raise CatalogError('Catalog changed. Close and reopen the application editor.')
        save_catalog(self.path, value)
        self._catalog = value

    def add_from_picker(self, selected_path, name, *, source='local'):
        self._local(source)
        if not selected_path:
            return None
        path = Path(selected_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
            raise CatalogError('Choose an existing EXE or LNK file on this PC.')
        # Reject UNC shares: a remote location must not become a launch authority.
        absolute = str(path.resolve())
        if absolute.startswith(('\\\\', '//')):
            raise CatalogError('Choose a file on a local drive.')
        item = {'id': uuid.uuid4().hex, 'name': name.strip(), 'path': absolute}
        value = copy.deepcopy(self._catalog)
        value['apps'].append(item)
        validate_catalog(value)
        self._commit(value)
        return copy.deepcopy(item)

    def rename(self, app_id, name, *, source='local'):
        self._local(source)
        value = copy.deepcopy(self._catalog)
        item = next((app for app in value['apps'] if app['id'] == app_id), None)
        if item is None:
            raise CatalogError('Application was not found.')
        item['name'] = name.strip()
        validate_catalog(value)
        self._commit(value)

    def remove(self, app_id, *, source='local'):
        self._local(source)
        value = copy.deepcopy(self._catalog)
        remaining = [app for app in value['apps'] if app['id'] != app_id]
        if len(remaining) == len(value['apps']):
            raise CatalogError('Application was not found.')
        value['apps'] = remaining
        self._commit(value)


_LABELS = {
    'en': {'title': 'Applications', 'intro': 'Choose programs on this PC to launch from your phone.',
           'hint': 'Only EXE programs and LNK shortcuts. Nothing is added automatically.',
           'name': 'Name', 'add': 'Add…', 'rename': 'Rename…', 'remove': 'Remove',
           'close': 'Close', 'pick': 'Choose a program on this PC', 'error': 'Could not update applications',
           'error_body': 'Check the local catalog and try again. No changes were saved.',
           'confirm': 'Remove this program from the phone list? The file will not be deleted.',
           'local': 'Editing is available only on this PC. Launch paths are never sent to the phone.'},
    'ru': {'title': 'Программы', 'intro': 'Выбери программы на этом ПК для запуска с телефона.',
           'hint': 'Только EXE и ярлыки LNK. Ничего не добавляется автоматически.',
           'name': 'Название', 'add': 'Добавить…', 'rename': 'Переименовать…', 'remove': 'Удалить',
           'close': 'Закрыть', 'pick': 'Выбери программу на этом ПК', 'error': 'Не удалось изменить список',
           'error_body': 'Проверь локальный каталог и попробуй снова. Изменения не сохранены.',
           'confirm': 'Убрать программу из списка телефона? Сам файл не будет удалён.',
           'local': 'Изменения доступны только на этом ПК. Пути программ не передаются телефону.'},
}


def show_apps(parent, data_dir: Path):
    """Open a non-modal local Tk editor, reading data_dir / 'apps.json'.

    Returns its Toplevel; no nested mainloop and no applications are launched.
    CatalogError is safe for the caller to display if initial loading fails.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    model = LocalAppsModel(data_dir)
    try:
        language = 'ru' if (locale.getlocale()[0] or '').lower().startswith('ru') else 'en'
    except (ValueError, TypeError):
        language = 'en'
    words = _LABELS[language]
    try:
        from theme import apply_theme, scrollable_card
    except ModuleNotFoundError:
        from desktop.theme import apply_theme, scrollable_card
    window = tk.Toplevel(parent)
    apply_theme(window)
    window.title(words['title'])
    window.geometry(f'680x{min(480, max(400, window.winfo_screenheight() - 100))}')
    window.minsize(520, 400)
    window.transient(parent)
    frame = scrollable_card(window)
    ttk.Label(frame, style='DB.Heading.TLabel', text=words['intro'], wraplength=580).pack(anchor='w')
    ttk.Label(frame, style='DB.Muted.TLabel', text=words['hint'], wraplength=580).pack(anchor='w', pady=(6, 12))
    tree_frame = ttk.Frame(frame, style='DB.Card.TFrame')
    tree_frame.pack(fill='both', expand=True)
    tree = ttk.Treeview(tree_frame, columns=('name',), show='headings', selectmode='browse')
    tree.heading('name', text=words['name'])
    tree.column('name', width=420, minwidth=200)
    scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')

    def refresh():
        tree.delete(*tree.get_children())
        for item in model.apps:
            tree.insert('', 'end', iid=item['id'], values=(item['name'],))
        update_buttons()

    def guarded(action):
        try:
            action()
            refresh()
        except (CatalogError, OSError, PermissionError):
            # No exception text: a platform file error can include a private path.
            messagebox.showerror(words['error'], words['error_body'], parent=window)

    def add():
        selected = filedialog.askopenfilename(parent=window, title=words['pick'],
                    filetypes=[('EXE / LNK', '*.exe *.lnk')])
        if not selected:
            return
        name = simpledialog.askstring(words['add'], words['name'], initialvalue=Path(selected).stem,
                                      parent=window)
        if name is not None:
            guarded(lambda: model.add_from_picker(selected, name))

    def rename():
        selected = tree.selection()
        if not selected:
            return
        item = next(app for app in model.apps if app['id'] == selected[0])
        name = simpledialog.askstring(words['rename'], words['name'], initialvalue=item['name'], parent=window)
        if name is not None:
            guarded(lambda: model.rename(item['id'], name))

    def remove():
        selected = tree.selection()
        if selected and messagebox.askyesno(words['remove'], words['confirm'], parent=window):
            guarded(lambda: model.remove(selected[0]))

    row = ttk.Frame(frame, style='DB.Card.TFrame')
    row.pack(fill='x', pady=12)
    ttk.Button(row, style='DB.Primary.TButton', text=words['add'], command=add).pack(side='left')
    rename_button = ttk.Button(row, text=words['rename'], command=rename)
    rename_button.pack(side='left', padx=8)
    remove_button = ttk.Button(row, style='DB.Danger.TButton', text=words['remove'], command=remove)
    remove_button.pack(side='left')
    ttk.Button(row, text=words['close'], command=window.destroy).pack(side='right')

    def update_buttons(*_):
        state = 'normal' if tree.selection() else 'disabled'
        rename_button.configure(state=state)
        remove_button.configure(state=state)

    tree.bind('<<TreeviewSelect>>', update_buttons)
    ttk.Label(frame, style='DB.Muted.TLabel', text=words['local'], wraplength=580).pack(anchor='w')
    refresh()
    return window
