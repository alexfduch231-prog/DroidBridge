"""Shared, dependency-free ttk theme matching DroidBridge's Android day palette.

apply_theme only changes appearance. It never owns window geometry, bindings,
application state, or lifecycle. Native Tk cannot reproduce Android's rounded
Material cards; white surfaces and spacing provide the same visual hierarchy.
"""
from tkinter import font, ttk

PALETTE = {
    'primary': '#1A63E7', 'background': '#F1F3F8', 'surface': '#FFFFFF',
    'surface_alt': '#F7F8FC', 'text': '#16181D', 'muted': '#5C6270',
    'danger': '#CC2F23', 'outline': '#8A909C', 'line': '#DDE2EC',
}


def apply_theme(window) -> None:
    """Apply the shared light theme to an existing Tk root or Toplevel."""
    style = ttk.Style(window)
    style.theme_use('clam')
    family = 'Segoe UI' if 'Segoe UI' in font.families(window) else font.nametofont('TkDefaultFont', root=window).actual('family')
    p = PALETTE
    window.configure(background=p['background'])
    style.configure('.', font=(family, 10), background=p['surface'],
                    foreground=p['text'], bordercolor=p['line'],
                    lightcolor=p['surface'], darkcolor=p['line'],
                    troughcolor=p['background'], selectbackground=p['primary'],
                    selectforeground=p['surface'])
    style.configure('TFrame', background=p['surface'])
    style.configure('DB.TFrame', background=p['background'])
    style.configure('DB.Card.TFrame', background=p['surface'], relief='flat', borderwidth=0)
    style.configure('DB.Accent.TFrame', background=p['primary'])
    for name in ('TLabel', 'DB.TLabel', 'DB.QR.TLabel'):
        style.configure(name, background=p['surface'], foreground=p['text'], font=(family, 10))
    style.configure('DB.Title.TLabel', background=p['background'], foreground=p['text'], font=(family, 25, 'bold'))
    style.configure('DB.Subtitle.TLabel', background=p['background'], foreground=p['muted'], font=(family, 10))
    style.configure('DB.Heading.TLabel', background=p['surface'], foreground=p['text'], font=(family, 13, 'bold'))
    style.configure('DB.Muted.TLabel', background=p['surface'], foreground=p['muted'])
    style.configure('DB.Danger.TLabel', background=p['surface'], foreground=p['danger'])
    style.configure('TButton', font=(family, 10), padding=(16, 10), relief='flat',
                    background=p['surface_alt'], foreground=p['text'], borderwidth=1,
                    bordercolor=p['line'], focusthickness=2, focuscolor=p['primary'])
    style.map('TButton', background=[('disabled', '#EDF0F5'), ('pressed', '#DDE6F7'), ('active', '#E9EFFB')],
              foreground=[('disabled', '#737A87')], bordercolor=[('focus', p['primary'])])
    style.configure('DB.TButton')
    for name, color, active, pressed in (
            ('DB.Primary.TButton', p['primary'], '#1557CD', '#1049AF'),
            ('DB.Danger.TButton', p['danger'], '#B6281E', '#992219')):
        style.configure(name, background=color, foreground=p['surface'],
                        bordercolor=color, focuscolor=p['surface'])
        style.map(name, background=[('disabled', '#E3E7EE'), ('pressed', pressed), ('active', active)],
                  foreground=[('disabled', '#737A87'), ('!disabled', p['surface'])],
                  bordercolor=[('disabled', '#E3E7EE'), ('!disabled', color)])
    style.configure('TEntry', padding=(10, 9), fieldbackground=p['surface_alt'],
                    foreground=p['text'], bordercolor=p['outline'], insertcolor=p['text'])
    style.map('TEntry', bordercolor=[('focus', p['primary'])],
              fieldbackground=[('disabled', '#EDF0F5')])
    style.configure('TCheckbutton', background=p['surface'], padding=(0, 6))
    style.configure('DB.Card.TCheckbutton', background=p['surface'])
    style.map('TCheckbutton', background=[('active', p['surface'])])
    style.configure('TSeparator', background=p['line'])
    style.configure('Vertical.TScrollbar', background='#CDD4E0', borderwidth=0,
                    arrowcolor=p['muted'], troughcolor=p['background'])


def card(parent, **kwargs) -> ttk.Frame:
    """Create a white card; callers choose its layout and content."""
    kwargs.setdefault('style', 'DB.Card.TFrame')
    kwargs.setdefault('padding', 20)
    return ttk.Frame(parent, **kwargs)


def scrollable_card(window) -> ttk.Frame:
    """Keep panel content reachable on short screens and at larger Tk scaling."""
    import tkinter as tk
    viewport = ttk.Frame(window, style='DB.TFrame')
    viewport.pack(fill='both', expand=True, padx=20, pady=20)
    canvas = tk.Canvas(viewport, background=PALETTE['background'], highlightthickness=0)
    vertical = ttk.Scrollbar(viewport, orient='vertical', command=canvas.yview)
    horizontal = ttk.Scrollbar(viewport, orient='horizontal', command=canvas.xview)
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    viewport.rowconfigure(0, weight=1)
    viewport.columnconfigure(0, weight=1)
    canvas.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    content = card(canvas)
    item = canvas.create_window(0, 0, anchor='nw', window=content)

    def resize(_event=None):
        canvas.itemconfigure(item, width=max(canvas.winfo_width(), content.winfo_reqwidth()),
                             height=max(canvas.winfo_height(), content.winfo_reqheight()))
        canvas.configure(scrollregion=canvas.bbox('all'))

    def reveal(event):
        widget = event.widget
        if not str(widget).startswith(str(content) + '.'):
            return
        top = widget.winfo_rooty() - content.winfo_rooty()
        left = widget.winfo_rootx() - content.winfo_rootx()
        if top < canvas.canvasy(0):
            canvas.yview_moveto(max(0, top - 8) / max(1, content.winfo_height()))
        elif top + widget.winfo_height() > canvas.canvasy(canvas.winfo_height()):
            canvas.yview_moveto((top + widget.winfo_height() + 8 - canvas.winfo_height()) / max(1, content.winfo_height()))
        if left < canvas.canvasx(0):
            canvas.xview_moveto(max(0, left - 8) / max(1, content.winfo_width()))
        elif left + widget.winfo_width() > canvas.canvasx(canvas.winfo_width()):
            canvas.xview_moveto((left + widget.winfo_width() + 8 - canvas.winfo_width()) / max(1, content.winfo_width()))

    def wheel(event):
        if event.delta:
            canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), 'units')

    content.bind('<Configure>', resize)
    canvas.bind('<Configure>', resize)
    window.bind('<FocusIn>', reveal, add='+')
    window.bind('<MouseWheel>', wheel, add='+')
    return content
