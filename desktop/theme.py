"""Root-scoped native Tk appearance with live updates and rounded ttk buttons."""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw
import sys
import tkinter as tk
from tkinter import TclError, font, ttk
from desktop.theme_settings import (THEME_MODES, load_theme_mode, save_theme_mode,
                                    system_theme)

_LIGHT = {
    'primary': '#1A63E7', 'background': '#F7F7F8', 'surface': '#F7F7F8',
    'surface_alt': '#EEEEF0', 'text': '#202024', 'muted': '#606068',
    'danger': '#BC2B21', 'outline': '#94949C', 'line': '#DEDEE2',
    'success': '#187645', 'button_text': '#FFFFFF', 'danger_button': '#CC2F23',
    'active': '#E9EFFB', 'pressed': '#DDE6F7', 'disabled': '#EDF0F5',
    'disabled_text': '#5C6270', 'primary_active': '#1557CD',
    'primary_pressed': '#1049AF', 'danger_active': '#B6281E', 'danger_pressed': '#992219',
}
# Historical imports keep their object identity. Root-local styling must never
# mutate this fallback: separate Tk interpreters may use different themes.
PALETTE = dict(_LIGHT)


def palette_for(mode, system=None) -> dict:
    if mode not in THEME_MODES:
        mode = 'system'
    if mode == 'system':
        mode = system if system in ('light', 'dark') else system_theme()
    if mode == 'light':
        return dict(_LIGHT)
    backgrounds = {
        'dark': ('#1B1B1B', '#232323', '#2D2D2D', '#285FC6'),
        'ocean': ('#081D30', '#102C43', '#18394F', '#17649B'),
        'forest': ('#10231C', '#19352A', '#214133', '#176B46'),
        'plum': ('#24152F', '#34203F', '#412B4D', '#8247A6'),
    }
    background, surface, alternate, accent = backgrounds[mode]
    def shade(color, factor):
        return '#' + ''.join(f'{round(int(color[i:i + 2], 16) * factor):02X}' for i in (1, 3, 5))
    return dict(_LIGHT, background=background, surface=background,
                surface_alt=alternate, primary=accent, text='#F5F7FC',
                muted='#C1CAD8', danger='#FFB6AE', success='#83DFAD',
                outline='#81818A', line='#48484E', active=alternate,
                pressed=background, disabled=alternate, disabled_text='#C1CAD8',
                primary_active=shade(accent, .88), primary_pressed=shade(accent, .74),
                danger_active='#B6281E', danger_pressed='#992219')


def _root(window):
    return window._root()


def palette_for_widget(widget):
    root = _root(widget)
    return getattr(root, '_droidbridge_palette', _LIGHT)


def font_family(window):
    """Use an installed Windows UI face, without downloading or installing fonts."""
    root = _root(window)
    cached = getattr(root, '_droidbridge_font', None)
    if cached is not None:
        return cached
    available = {name.casefold(): name for name in font.families(root)}
    for candidate in ('Segoe UI Variable Text', 'Segoe UI Variable', 'Segoe UI'):
        if candidate.casefold() in available:
            family = available[candidate.casefold()]
            break
    else:
        family = font.nametofont('TkDefaultFont', root=root).actual('family')
    root._droidbridge_font = family
    return family


def _rounded_buttons(root, style, p):
    """Install stretchable borders once; refresh a bounded set of Tk images in place.

    The label/padding remain ttk elements: commands, focus traversal, keyboard
    bindings, state and accessibility still belong to the real TButton widget.
    Corner pixels match the containing surface. ttk paints its style background
    before drawing elements, so alpha-only corners would reveal a square accent.
    """
    images = getattr(root, '_droidbridge_button_images', None)
    if images is None:
        images = root._droidbridge_button_images = {}
    signature = tuple(sorted(p.items()))
    refresh = getattr(root, '_droidbridge_button_signature', None) != signature
    specs = (
        ('neutral', 'TButton', p['surface_alt'], p['active'], p['pressed'], 11, p['surface_alt']),
        ('background', 'DB.Sidebar.TButton', p['surface_alt'], p['active'], p['pressed'], 11, p['surface_alt']),
        ('primary', 'DB.Primary.TButton', p['surface_alt'], p['active'], p['pressed'], 11, p['surface_alt']),
        ('danger', 'DB.Danger.TButton', _LIGHT['danger'], p['danger_active'], p['danger_pressed'], 11, _LIGHT['danger']),
        ('nav', 'DB.Nav.TButton', p['background'], p['surface_alt'], p['pressed'], 8, p['background']),
        ('selected', 'DB.Nav.Selected.TButton', p['surface_alt'], p['active'], p['pressed'], 8, p['surface_alt']),
    )
    existing = set(style.element_names())
    for role, name, normal, active, pressed, radius, outline in specs:
        states = (('normal', normal), ('disabled', p['disabled']),
                  ('pressed_focus', pressed), ('pressed', pressed),
                  ('active_focus', active), ('active', active), ('focus', normal))
        for state, fill in states:
            key = role, state
            if key not in images or refresh:
                # Four-times supersampling gives smooth edges without new deps.
                # Tk tiles the nine-slice center (it does not scale it). A 3px
                # center causes thousands of native photo draws per button.
                size, supersample = 51, 4
                backdrop = p['background'] if role in ('background', 'nav', 'selected') else p['surface']
                tile = Image.new('RGBA', (size * supersample, size * supersample), backdrop)
                draw = ImageDraw.Draw(tile)
                focused = state in ('focus', 'active_focus', 'pressed_focus')
                ring = p['button_text'] if role == 'danger' else p['primary']
                edge = ring if focused else (fill if state != 'normal' else outline)
                inset = 1 if focused else 2
                box = (inset * supersample, inset * supersample,
                       (size - inset) * supersample - 1, (size - inset) * supersample - 1)
                draw.rounded_rectangle(box, radius=radius * supersample, fill=fill,
                                       outline=edge, width=(2 if focused else 1) * supersample)
                tile = tile.resize((size, size), Image.Resampling.LANCZOS)
                encoded = BytesIO()
                tile.save(encoded, format='PNG')
                if key not in images:
                    images[key] = tk.PhotoImage(master=root, data=encoded.getvalue())
                else:
                    # Reconfigure the existing Tcl image: old widgets/elements keep
                    # valid names and repeated switches cannot grow the cache.
                    images[key].configure(data=encoded.getvalue())
        element = 'DB.Rounded.' + role
        if element not in existing:
            style.element_create(element, 'image', images[role, 'normal'],
                                 ('disabled', images[role, 'disabled']),
                                 ('pressed', 'focus', images[role, 'pressed_focus']),
                                 ('pressed', images[role, 'pressed']),
                                 ('active', 'focus', images[role, 'active_focus']),
                                 ('active', images[role, 'active']),
                                 ('focus', images[role, 'focus']),
                                 border=12, padding=0, width=27, height=27, sticky='nsew')
        style.layout(name, [(element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [
                ('Button.label', {'sticky': 'nsew'})]})]})])
    root._droidbridge_button_signature = signature


def _rounded_scrollbars(root, style, p):
    """Skin real ttk scrollbars; retain native thumb hit-testing and bindings.

    Eight root-owned images are refreshed in place, independently of buttons.
    Opaque corners and explicit clam maps keep every state on the page surface.
    The 27px nine-slice center avoids a per-pixel native photo tiling hot path.
    """
    images = getattr(root, '_droidbridge_scrollbar_images', None)
    if images is None:
        images = root._droidbridge_scrollbar_images = {}
    density = float(root.tk.call('tk', 'scaling')) / (4 / 3)
    width = max(10, round(11 * density))
    signature = (tuple(sorted(p.items())), width)
    refresh = getattr(root, '_droidbridge_scrollbar_signature', None) != signature
    colors = (('normal', p['line']), ('active', p['outline']),
              ('pressed', p['muted']), ('disabled', p['surface_alt']))
    existing = set(style.element_names())
    for orient in ('Vertical', 'Horizontal'):
        vertical = orient == 'Vertical'
        for state, fill in colors:
            key = orient, state
            if key not in images or refresh:
                size = (width, 51) if vertical else (51, width)
                scale = 4
                tile = Image.new('RGB', tuple(n * scale for n in size), p['background'])
                draw = ImageDraw.Draw(tile)
                inset = max(2, round(2 * density))
                draw.rounded_rectangle((inset * scale, inset * scale,
                                        (size[0] - inset) * scale - 1,
                                        (size[1] - inset) * scale - 1),
                                       radius=max(1, (width - 2 * inset) / 2) * scale,
                                       fill=fill)
                tile = tile.resize(size, Image.Resampling.LANCZOS)
                encoded = BytesIO()
                tile.save(encoded, format='PNG')
                if key not in images:
                    images[key] = tk.PhotoImage(master=root, data=encoded.getvalue())
                else:
                    images[key].configure(data=encoded.getvalue())
        element = 'DB.' + orient + '.Scrollbar.thumb'
        if element not in existing:
            style.element_create(element, 'image', images[orient, 'normal'],
                                 ('disabled', images[orient, 'disabled']),
                                 ('pressed', images[orient, 'pressed']),
                                 ('active', images[orient, 'active']),
                                 border=(0, 12, 0, 12) if vertical else (12, 0, 12, 0),
                                 sticky='nsew')
        name = orient + '.TScrollbar'
        style.layout(name, [(orient + '.Scrollbar.trough', {
            'sticky': 'nsew', 'children': [(element, {'sticky': 'nsew'})]})])
        style.configure(name, background=p['line'], troughcolor=p['background'],
                        bordercolor=p['background'], lightcolor=p['background'],
                        darkcolor=p['background'], arrowcolor=p['background'],
                        borderwidth=0, relief='flat', troughrelief='flat',
                        arrowsize=0, width=width)
        # Override inherited clam maps, including its pressed/active light edges.
        style.map(name, background=[('disabled', p['surface_alt']),
                                    ('pressed', p['muted']), ('active', p['outline']),
                                    ('!disabled', p['line'])],
                  **{option: [('disabled', p['background']), ('!disabled', p['background'])]
                     for option in ('troughcolor', 'bordercolor', 'lightcolor',
                                    'darkcolor', 'arrowcolor')})
    root._droidbridge_scrollbar_signature = signature


def _apply_styles(window, p):
    style = ttk.Style(window)
    if style.theme_use() != 'clam':
        style.theme_use('clam')
    root = _root(window)
    family = font_family(window)
    window.configure(background=p['background'])
    style.configure('.', font=(family, 10), background=p['surface'],
                    foreground=p['text'], bordercolor=p['line'],
                    lightcolor=p['surface'], darkcolor=p['line'],
                    troughcolor=p['background'], selectbackground=p['primary'],
                    selectforeground=p['button_text'])
    for name, color in (('TFrame', p['surface']), ('DB.TFrame', p['background']),
                        ('DB.Card.TFrame', p['surface']), ('DB.Accent.TFrame', p['primary'])):
        style.configure(name, background=color, relief='flat', borderwidth=0)
    for name in ('TLabel', 'DB.TLabel'):
        style.configure(name, background=p['surface'], foreground=p['text'], font=(family, 10))
    # QR pixels and their white quiet zone are intentionally not themed.
    style.configure('DB.QR.TLabel', background='#FFFFFF', foreground='#16181D', font=(family, 10))
    style.configure('DB.Title.TLabel', background=p['background'], foreground=p['text'], font=(family, 12, 'bold'))
    style.configure('DB.Subtitle.TLabel', background=p['background'], foreground=p['muted'], font=(family, 10))
    style.configure('DB.Heading.TLabel', background=p['surface'], foreground=p['text'], font=(family, 13, 'bold'))
    style.configure('DB.Muted.TLabel', background=p['surface'], foreground=p['muted'])
    style.configure('DB.Danger.TLabel', background=p['surface'], foreground=p['danger'])
    # Tk scaling is pixels/point (96 DPI = 4/3); use pixel-sized button fonts
    # so reapplying after a DPI change does not reuse stale Tk font metrics.
    scaling = float(root.tk.call('tk', 'scaling'))
    density = scaling / (4 / 3)
    button_font = (family, -max(10, round(10 * scaling)))
    padding = (max(12, round(16 * density)), max(8, round(13 * density)))
    style.configure('TButton', font=button_font, padding=padding, relief='flat',
                    background=p['surface_alt'], foreground=p['text'], borderwidth=0,
                    bordercolor=p['surface_alt'], focusthickness=2, focuscolor=p['primary'])
    style.map('TButton', background=[('disabled', p['disabled']), ('pressed', p['pressed']), ('active', p['active'])],
              foreground=[('disabled', p['disabled_text'])], bordercolor=[('focus', p['primary'])])
    style.configure('DB.TButton')
    for name, selected in (('DB.Nav.TButton', False), ('DB.Nav.Selected.TButton', True)):
        background = p['surface_alt'] if selected else p['background']
        style.configure(name, background=background, foreground=p['text'],
                        anchor='w', padding=(padding[0], max(8, round(8 * density))), borderwidth=0,
                        font=button_font, focuscolor=p['primary'])
        style.map(name, background=[('pressed', p['pressed']), ('active', p['surface_alt'])],
                  foreground=[('disabled', p['disabled_text']), ('!disabled', p['text'])],
                  bordercolor=[('focus', p['primary'])])
    # Danger text on dark surfaces is pale; danger buttons retain a dark red
    # background so their fixed white caption remains readable.
    for name, color, active, pressed in (
            ('DB.Primary.TButton', p['primary'], p['primary_active'], p['primary_pressed']),
            ('DB.Danger.TButton', _LIGHT['danger'], p['danger_active'], p['danger_pressed'])):
        style.configure(name, background=color, foreground=p['button_text'],
                        bordercolor=color, focuscolor=p['button_text'])
        style.map(name, background=[('disabled', p['disabled']), ('pressed', pressed), ('active', active)],
                  foreground=[('disabled', p['disabled_text']), ('!disabled', p['button_text'])],
                  bordercolor=[('disabled', p['disabled']), ('!disabled', color)])
    # Primary actions use the same quiet fill as ordinary controls; the accent
    # remains a focus/selection cue rather than a large saturated rectangle.
    style.configure('DB.Primary.TButton', background=p['surface_alt'],
                    foreground=p['text'], bordercolor=p['surface_alt'], focuscolor=p['primary'])
    style.map('DB.Primary.TButton',
              background=[('disabled', p['disabled']), ('pressed', p['pressed']), ('active', p['active'])],
              foreground=[('disabled', p['disabled_text']), ('!disabled', p['text'])],
              bordercolor=[('focus', p['primary']), ('!focus', p['surface_alt'])])
    _rounded_buttons(root, style, p)
    for name in ('TEntry', 'TCombobox'):
        style.configure(name, padding=(10, 9), fieldbackground=p['surface_alt'],
                        background=p['surface_alt'], foreground=p['text'],
                        arrowcolor=p['text'], bordercolor=p['outline'], insertcolor=p['text'])
        style.map(name, bordercolor=[('focus', p['primary'])],
                  fieldbackground=[('disabled', p['disabled']), ('readonly', p['surface_alt'])],
                  foreground=[('disabled', p['disabled_text']), ('readonly', p['text'])],
                  selectbackground=[('!disabled', p['primary'])],
                  selectforeground=[('!disabled', p['button_text'])])
    for name in ('TCheckbutton', 'TRadiobutton', 'DB.Card.TCheckbutton'):
        style.configure(name, background=p['surface'], foreground=p['text'], padding=(0, 6))
        style.map(name, background=[('active', p['surface'])], foreground=[('disabled', p['disabled_text'])])
    style.configure('Treeview', background=p['surface_alt'], fieldbackground=p['surface_alt'],
                    foreground=p['text'], bordercolor=p['outline'])
    style.map('Treeview', background=[('disabled', p['disabled']), ('selected', p['primary'])],
              foreground=[('disabled', p['disabled_text']), ('selected', p['button_text'])])
    style.configure('Treeview.Heading', background=p['surface'], foreground=p['text'],
                    bordercolor=p['line'])
    style.map('Treeview.Heading', background=[('pressed', p['pressed']), ('active', p['active'])],
              foreground=[('disabled', p['disabled_text']), ('!disabled', p['text'])])
    style.configure('TSeparator', background=p['line'])
    _rounded_scrollbars(root, style, p)
    # Combobox popup is a native Tk listbox, not a ttk widget.
    for option, value in (('background', p['surface_alt']), ('foreground', p['text']),
                          ('selectBackground', p['primary']), ('selectForeground', p['button_text'])):
        window.option_add('*TCombobox*Listbox.' + option, value, 80)


def _walk_colors(widget, old, new):
    """Only replace known appearance colors; never touch pixels or widget state."""
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        widget.configure(background=new['background'])
    elif not isinstance(widget, ttk.Widget):
        options = widget.keys()
        for option in ('background', 'foreground', 'insertbackground', 'selectbackground',
                       'selectforeground', 'highlightbackground', 'highlightcolor',
                       'readonlybackground', 'disabledbackground', 'disabledforeground'):
            if option not in options:
                continue
            current = str(widget.cget(option)).lower()
            # QR quiet zones and explicit image backgrounds stay white.
            if (option in ('background', 'highlightbackground')
                    and current in ('#ffffff', 'white')
                    and 'image' in options and widget.cget('image')):
                continue
            for key, color in old.items():
                if current == color.lower():
                    widget.configure(**{option: new[key]})
                    break
    for child in widget.winfo_children():
        _walk_colors(child, old, new)


def apply_theme(window) -> None:
    """Compatibility wrapper: inherit this interpreter's context, never globals."""
    root = _root(window)
    if not hasattr(root, '_droidbridge_palette'):
        root._droidbridge_palette = palette_for('system')
    _apply_styles(window, root._droidbridge_palette)
    asset_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    try:
        window.iconbitmap(str(asset_root / 'assets' / 'droidbridge.ico'))
    except TclError:
        pass


class ThemeController:
    """One controller per Tk interpreter; all work runs on Tk's owning thread."""
    def __new__(cls, root, data_dir):
        owner = _root(root)
        existing = getattr(owner, 'theme_controller', None)
        if existing is not None and not existing._disposed:
            return existing
        return super().__new__(cls)

    def __init__(self, root, data_dir):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self.root = _root(root)
        self.data_dir = Path(data_dir)
        self.mode = load_theme_mode(data_dir)
        self.palette = palette_for(self.mode)
        self._disposed = False
        self._timer = None
        self.root.theme_controller = self.root._theme_controller = self
        self.root._droidbridge_palette = self.palette
        apply_theme(self.root)
        self._destroy_binding = self.root.bind('<Destroy>', self._on_destroy, add='+')
        self._schedule()

    def _schedule(self):
        if not self._disposed and self.mode == 'system' and self._timer is None:
            self._timer = self.root.after(1500, self._poll_system)

    def _cancel_timer(self):
        if self._timer is not None:
            try:
                self.root.after_cancel(self._timer)
            except TclError:
                pass
            self._timer = None

    def _poll_system(self):
        self._cancel_timer()
        if self._disposed or self.mode != 'system':
            return
        palette = palette_for('system')
        if palette != self.palette:
            self._apply(palette)
        self._schedule()

    def _apply(self, palette):
        old = self.palette.copy()
        self.palette.clear()
        self.palette.update(palette)
        self.root._droidbridge_palette = self.palette
        _apply_styles(self.root, self.palette)
        _walk_colors(self.root, old, self.palette)
        self.root.event_generate('<<DroidBridgeThemeChanged>>')

    def set_mode(self, mode):
        if self._disposed:
            return
        # Save before changing anything: failures must leave selection and UI true.
        save_theme_mode(self.data_dir, mode)
        palette = palette_for(mode)
        self.mode = mode
        self._cancel_timer()
        self._apply(palette)
        self._schedule()

    def _on_destroy(self, event):
        if event.widget is self.root:
            self.dispose()

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self._cancel_timer()
        if self._destroy_binding:
            try:
                self.root.unbind('<Destroy>', self._destroy_binding)
            except TclError:
                pass
            self._destroy_binding = None


def card(parent, **kwargs) -> ttk.Frame:
    """Create a borderless main-surface card; callers choose its layout."""
    kwargs.setdefault('style', 'DB.Card.TFrame')
    kwargs.setdefault('padding', 20)
    return ttk.Frame(parent, **kwargs)


def scrollable_card(window) -> ttk.Frame:
    """Keep panel content reachable on short screens and at larger Tk scaling."""
    import tkinter as tk
    viewport = ttk.Frame(window, style='DB.TFrame')
    viewport.pack(fill='both', expand=True, padx=20, pady=20)
    canvas = tk.Canvas(viewport, background=palette_for_widget(window)['background'],
                       highlightthickness=0, borderwidth=0, relief='flat')
    vertical = ttk.Scrollbar(viewport, orient='vertical', command=canvas.yview)
    horizontal = ttk.Scrollbar(viewport, orient='horizontal', command=canvas.xview)
    viewport.rowconfigure(0, weight=1)
    viewport.columnconfigure(0, weight=1)
    canvas.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    vertical.grid_remove()
    horizontal.grid_remove()
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    content = card(canvas)
    item = canvas.create_window(0, 0, anchor='nw', window=content)

    button_text = {}

    def button_insets(button, style):
        # ttk padding is scaled with the font; a fixed 44px allowance clips
        # captions at high DPI even when their containing card fits the canvas.
        padding = button.tk.splitlist(style.lookup(button.cget('style') or 'TButton', 'padding'))
        pixels = [button.winfo_pixels(value) for value in padding]
        horizontal = (pixels[0] + pixels[2] if len(pixels) >= 3
                      else 2 * pixels[0] if pixels else 0)
        return horizontal + 8

    def fit_controls(parent, available):
        """Reflow text and action groups without reducing the user's font size."""
        children = parent.winfo_children()
        packed_buttons = [child for child in children
                          if isinstance(child, ttk.Button) and child.winfo_manager() == 'pack']
        if packed_buttons and len(packed_buttons) == len(children):
            def natural_width(button):
                original = button_text.get(button, (str(button.cget('text')), ''))[0]
                style = ttk.Style(button)
                button_font = style.lookup(button.cget('style') or 'TButton', 'font')
                return max(button.winfo_reqwidth() + 8,
                           int(button.tk.call('font', 'measure', button_font, original.replace('\n', ' '))) + button_insets(button, style) + 8)
            stacked = sum(natural_width(child) for child in children) > available
            for child in children:
                child.pack_configure(side='top' if stacked else 'left',
                                     anchor='w', padx=0 if stacked else 4,
                                     pady=4 if stacked else 0)
        for child in children:
            if isinstance(child, ttk.Label) and (child.cget('text') or child.cget('textvariable')):
                child.configure(wraplength=max(40, available))
            elif isinstance(child, ttk.Button):
                current = str(child.cget('text'))
                original, rendered = button_text.get(child, (current, current))
                if current != rendered:
                    original = current
                style = ttk.Style(child)
                button_font = style.lookup(child.cget('style') or 'TButton', 'font')
                lines, line = [], ''
                for word in original.replace('\n', ' ').split():
                    candidate = f'{line} {word}'.strip()
                    if line and int(child.tk.call('font', 'measure', button_font, candidate)) > max(40, available - button_insets(child, style)):
                        lines.append(line)
                        line = word
                    else:
                        line = candidate
                lines.append(line)
                rendered = '\n'.join(lines)
                button_text[child] = (original, rendered)
                if current != rendered:
                    child.configure(text=rendered)
            if isinstance(child, ttk.Frame):
                fit_controls(child, available)

    def minimum_width(parent):
        """Natural minimum excluding fields/tables designed to shrink to fit."""
        horizontal, vertical = 0, 0
        for child in parent.winfo_children():
            if isinstance(child, ttk.Frame):
                required = minimum_width(child)
            elif isinstance(child, (ttk.Entry, ttk.Combobox, ttk.Treeview)):
                required = 0
            else:
                required = child.winfo_reqwidth()
            if child.winfo_manager() == 'pack':
                info = child.pack_info()
                padx = child.tk.splitlist(str(info['padx']))
                required += sum(child.winfo_pixels(value) for value in padx) * (2 if len(padx) == 1 else 1)
                if str(info['side']) in ('left', 'right'):
                    horizontal += required
                else:
                    vertical = max(vertical, required)
            else:
                vertical = max(vertical, required)
        padding = parent.tk.splitlist(parent.cget('padding'))
        pixels = [parent.winfo_pixels(value) for value in padding]
        inset = pixels[0] + pixels[2] if len(pixels) >= 3 else 2 * pixels[0] if pixels else 0
        return max(horizontal, vertical) + inset

    def resize(_event=None):
        width = canvas.winfo_width()
        if width > 100:
            fit_controls(content, max(40, width - 40))
        # Stretch ordinary content, but keep genuinely unbreakable controls at
        # their natural width so horizontal scrolling can reach their far edge.
        requested_width = minimum_width(content)
        canvas.itemconfigure(item, width=max(width, requested_width))
        # Base overflow on the full viewport, not the already reduced canvas:
        # otherwise a visible bar can keep itself alive after content shrinks.
        full_width, full_height = viewport.winfo_width(), viewport.winfo_height()
        need_x = requested_width > full_width
        need_y = content.winfo_reqheight() > full_height - (horizontal.winfo_reqheight() if need_x else 0)
        if need_y:
            need_x = requested_width > full_width - vertical.winfo_reqwidth()
        if need_x:
            need_y = content.winfo_reqheight() > full_height - horizontal.winfo_reqheight()
        for bar, needed in ((vertical, need_y), (horizontal, need_x)):
            if needed and not bar.winfo_manager():
                bar.grid()
            elif not needed and bar.winfo_manager():
                bar.grid_remove()
        # Let Tk derive the item height from its requested geometry. Explicit
        # heights during Configure can strand children at the previous height.
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
        if not str(event.widget).startswith(str(viewport) + '.'):
            return
        if viewport.winfo_ismapped() and event.delta:
            canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), 'units')

    content.bind('<Configure>', resize)
    canvas.bind('<Configure>', resize)
    # Tk sends descendant events to their toplevel bindtag, not arbitrary
    # ancestor frames. Bind there so embedded pages retain focus scrolling.
    owner = window.winfo_toplevel()
    def descendant_resize(event):
        # A constrained item's requested width can change without changing the
        # item's actual width; child Configure events still expose that change.
        if str(event.widget).startswith(str(content) + '.'):
            resize()

    bindings = [(event, owner.bind(event, callback, add='+'))
                for event, callback in (('<FocusIn>', reveal), ('<MouseWheel>', wheel),
                                        ('<Configure>', descendant_resize))]

    def cleanup(event):
        if event.widget is not viewport:
            return
        for sequence, identifier in bindings:
            owner.unbind(sequence, identifier)
        bindings.clear()

    viewport.bind('<Destroy>', cleanup, add='+')
    return content
