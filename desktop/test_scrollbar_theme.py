"""Mapped real-ttk scrollbar regressions; no screen capture or global bindings."""
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from desktop import theme


class ScrollbarThemeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        previous = self.root.tk.call('tk', 'scaling')
        self.addCleanup(self.root.tk.call, 'tk', 'scaling', previous)
        self.root.tk.call('tk', 'scaling', 4 / 3)
        self.root.geometry('420x320')
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        theme.apply_theme(self.root)

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def settle(self):
        for _ in range(5):
            self.root.update()

    def test_both_default_styles_override_clam_colors_in_every_state(self):
        # Missing maps leaks clam's light active/pressed borders in dark themes.
        style = ttk.Style(self.root)
        bars = [ttk.Scrollbar(self.root, orient=orient) for orient in ('vertical', 'horizontal')]
        for bar in bars:
            bar.pack(fill='y' if str(bar.cget('orient')) == 'vertical' else 'x')
            bar.set(.15, .55)
        for mode in ('light', 'dark', 'ocean', 'forest', 'plum', 'system'):
            p = theme.palette_for(mode, system='dark')
            theme._apply_styles(self.root, p)
            self.settle()
            for orient, bar in zip(('Vertical', 'Horizontal'), bars):
                name = orient + '.TScrollbar'
                layout = str(style.layout(name)).lower()
                self.assertNotIn('arrow', layout)
                self.assertIn('thumb', layout)
                self.assertTrue(bar.winfo_ismapped())
                self.assertEqual(bar.winfo_class(), 'TScrollbar')
                self.assertIn('TScrollbar', bar.bindtags())
                self.assertEqual(int(style.lookup(name, 'arrowsize')), 0)
                for state in ((), ('active',), ('pressed',), ('disabled',), ('focus',),
                              ('active', 'focus'), ('pressed', 'active'), ('disabled', 'active')):
                    with self.subTest(mode=mode, orient=orient, state=state):
                        expected = (p['surface_alt'] if 'disabled' in state else
                                    p['muted'] if 'pressed' in state else
                                    p['outline'] if 'active' in state else p['line'])
                        self.assertEqual(style.lookup(name, 'background', state), expected)
                        for option in ('troughcolor', 'bordercolor', 'lightcolor', 'darkcolor'):
                            self.assertEqual(style.lookup(name, option, state), p['background'])
                cross = bar.winfo_reqwidth() if orient == 'Vertical' else bar.winfo_reqheight()
                self.assertGreaterEqual(cross, 10)
                self.assertLessEqual(cross, 12)

    def test_live_images_are_rounded_opaque_root_local_and_bounded(self):
        # Replacing image names on each switch leaks Tcl images and strands widgets.
        with tempfile.TemporaryDirectory() as data, patch.object(theme, 'system_theme', return_value='dark'):
            controller = theme.ThemeController(self.root, data)
            self.addCleanup(controller.dispose)
            self.settle()
            images = getattr(self.root, '_droidbridge_scrollbar_images', {})
            self.assertEqual(len(images), 8)
            names = {key: str(image) for key, image in images.items()}
            initial = set(self.root.tk.call('image', 'names'))
            events = []
            self.root.bind('<<DroidBridgeThemeChanged>>', lambda event: events.append(event))
            for mode in ('light', 'dark', 'ocean', 'forest', 'plum', 'system') * 2:
                controller.set_mode(mode)
                self.settle()
                p = controller.palette
                rgb = lambda color: tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
                for (orient, state), image in images.items():
                    fill = {'normal': p['line'], 'active': p['outline'],
                            'pressed': p['muted'], 'disabled': p['surface_alt']}[state]
                    self.assertEqual(image.get(image.width() // 2, image.height() // 2), rgb(fill))
                    self.assertEqual(image.get(0, 0), rgb(p['background']))
                    self.assertFalse(image.transparency_get(0, 0))
                self.assertEqual({key: str(image) for key, image in images.items()}, names)
                self.assertEqual(set(self.root.tk.call('image', 'names')), initial)
                self.assertEqual(len(self.root._droidbridge_button_images), 42)
            self.assertEqual(len(events), 12)

    def test_second_interpreter_keeps_its_palette_and_images_after_first_is_destroyed(self):
        # Global image ownership would recolor or delete another root's thumb.
        import gc
        other = tk.Tk()
        try:
            theme._apply_styles(other, theme.palette_for('ocean'))
            theme._apply_styles(self.root, theme.palette_for('light'))
            bar = ttk.Scrollbar(self.root)
            bar.pack(fill='y')
            bar.set(.1, .6)
            self.settle()
            local = self.root._droidbridge_scrollbar_images['Vertical', 'normal']
            foreign = other._droidbridge_scrollbar_images['Vertical', 'normal']
            self.assertIsNot(local, foreign)
            theme._apply_styles(other, theme.palette_for('plum'))
            gc.collect()
            self.assertEqual(local.get(0, 0), (247, 247, 248))
            self.assertEqual(foreign.get(0, 0), (36, 21, 47))
            self.assertEqual(ttk.Style(self.root).lookup('Vertical.TScrollbar', 'troughcolor'), '#F7F7F8')
        finally:
            other.destroy()
        gc.collect()
        self.settle()
        self.assertTrue(bar.winfo_ismapped())
        self.assertEqual(bar.get(), (.1, .6))
        self.assertEqual(local.get(0, 0), (247, 247, 248))

    def test_dpi_reapply_resizes_existing_images_without_growing_cache(self):
        # Static pixel width becomes a hairline at high DPI; reapply must resize it.
        style = ttk.Style(self.root)
        names = set(self.root.tk.call('image', 'names'))
        widths = []
        for scaling in (4 / 3, 2, 3, 4 / 3):
            self.root.tk.call('tk', 'scaling', scaling)
            theme.apply_theme(self.root)
            bars = [ttk.Scrollbar(self.root, orient=orient) for orient in ('vertical', 'horizontal')]
            cross = (bars[0].winfo_reqwidth(), bars[1].winfo_reqheight())
            self.assertEqual(cross[0], cross[1])
            widths.append(cross[0])
            self.assertEqual(set(self.root.tk.call('image', 'names')), names)
            for bar in bars:
                bar.destroy()
        self.assertGreater(widths[1], widths[0])
        self.assertGreater(widths[2], widths[1])
        self.assertEqual(widths[3], widths[0])

    def test_native_thumb_drag_and_trough_commands_survive_arrowless_layout(self):
        # A decorative image without a *.thumb element breaks ttk's native drag.
        for orient in ('vertical', 'horizontal'):
            calls = []
            bar = ttk.Scrollbar(self.root, orient=orient, command=lambda *args: calls.append(args), takefocus=True)
            bar.pack(fill='y' if orient == 'vertical' else 'x', expand=True)
            bar.set(.2, .5)
            self.settle()
            self.assertEqual(bar.get(), (.2, .5))
            long_size = bar.winfo_height() if orient == 'vertical' else bar.winfo_width()
            cross = bar.winfo_width() if orient == 'vertical' else bar.winfo_height()
            point = lambda pos: (cross // 2, pos) if orient == 'vertical' else (pos, cross // 2)
            thumb = [pos for pos in range(long_size) if 'thumb' in bar.identify(*point(pos))]
            self.assertTrue(thumb)
            middle = (thumb[0] + thumb[-1]) // 2
            bar.event_generate('<ButtonPress-1>', x=point(middle)[0], y=point(middle)[1])
            bar.event_generate('<B1-Motion>', x=point(middle + 25)[0], y=point(middle + 25)[1])
            bar.event_generate('<ButtonRelease-1>', x=point(middle + 25)[0], y=point(middle + 25)[1])
            self.assertTrue(any(args[0] == 'moveto' and float(args[1]) > .2 for args in calls), calls)
            bar.event_generate('<ButtonPress-1>', x=point(long_size - 3)[0], y=point(long_size - 3)[1])
            bar.event_generate('<ButtonRelease-1>', x=point(long_size - 3)[0], y=point(long_size - 3)[1])
            self.assertIn(('scroll', '1', 'pages'), calls)
            self.assertTrue(bar.cget('takefocus'))
            bar.destroy()

    def test_overflow_both_axes_shows_themed_bars_and_shrink_hides_them(self):
        # Theme installation must leave actual viewport auto-hide and fractions intact.
        content = theme.scrollable_card(self.root)
        canvas = content.master
        fixed = tk.Canvas(content, width=900, height=800, highlightthickness=0)
        fixed.pack()
        self.settle()
        bars = [w for w in canvas.master.winfo_children() if isinstance(w, ttk.Scrollbar)]
        self.assertEqual(len(bars), 2)
        for bar in bars:
            self.assertTrue(bar.winfo_ismapped())
            self.assertLess(bar.get()[1], 1)
            self.assertLessEqual(bar.winfo_reqwidth() if str(bar.cget('orient')) == 'vertical'
                                 else bar.winfo_reqheight(), 12)
        fixed.configure(width=100, height=60)
        self.settle()
        self.assertTrue(all(not bar.winfo_ismapped() for bar in bars))


if __name__ == '__main__':
    unittest.main()
