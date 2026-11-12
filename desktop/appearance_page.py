"""Embedded appearance settings composed with the existing media setup page."""
import tkinter as tk
from tkinter import messagebox, ttk

THEME_LABELS = {
    'system': 'Как в Windows', 'light': 'Светлая', 'dark': 'Тёмная',
    'ocean': 'Океан', 'forest': 'Лес', 'plum': 'Слива',
}


def build_appearance_page(parent, data_dir, controller):
    from desktop.media_setup import build_media_page
    page = ttk.Frame(parent, style='DB.TFrame')
    media = build_media_page(page, data_dir)
    media.pack(fill='both', expand=True)
    # Reuse the media page's existing scrolling content, keeping every setting
    # reachable together on small screens without changing media callbacks.
    def find_content(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Canvas):
                frames = [item for item in child.winfo_children() if isinstance(item, ttk.Frame)]
                if frames:
                    return frames[0]
            found = find_content(child)
            if found is not None:
                return found
        return None
    content = find_content(media)
    if content is None:
        content = page
    existing = content.pack_slaves()
    section = ttk.Frame(content, style='DB.Card.TFrame', padding=(0, 0, 0, 20))
    section.pack(fill='x', before=existing[0] if existing else None)
    ttk.Label(section, text='Оформление', style='DB.Heading.TLabel').pack(anchor='w')
    ttk.Label(section, text='Тема меняется сразу, без перезапуска. «Как в Windows» следует теме приложений системы.',
              style='DB.Muted.TLabel', wraplength=420).pack(anchor='w', pady=(8, 10))
    mode_var = tk.StringVar(page, value=THEME_LABELS[controller.mode])
    selector = ttk.Combobox(section, state='readonly', textvariable=mode_var,
                            values=tuple(THEME_LABELS.values()), width=20)
    selector.pack(fill='x')

    def select(_event=None):
        mode = next((key for key, label in THEME_LABELS.items() if label == mode_var.get()), controller.mode)
        try:
            controller.set_mode(mode)
        except (OSError, ValueError) as error:
            mode_var.set(THEME_LABELS[controller.mode])
            messagebox.showerror('Не удалось сохранить тему',
                                 'Тема не изменена. Проверь доступ к папке данных.\n' + str(error), parent=page)

    selector.bind('<<ComboboxSelected>>', select)
    disposed = False

    def dispose():
        nonlocal disposed
        if disposed:
            return
        disposed = True
        media.dispose()

    page.dispose = dispose
    page.media_page = media
    page.mode_var = mode_var
    page.selector = selector
    return page
