"""Mapped Tk regressions for quiet surfaces and overflow-only scrolling."""
import tempfile
import tkinter as tk
from tkinter import font, ttk
import unittest
from unittest.mock import patch

from desktop import theme


class QuietSurfacesTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('940x760')
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        previous = self.root.tk.call('tk', 'scaling')
        self.addCleanup(self.root.tk.call, 'tk', 'scaling', previous)
        self.root.tk.call('tk', 'scaling', 4 / 3)
        theme.apply_theme(self.root)

    def tearDown(self):
        self.assertEqual(self.errors, [], 'Tk callbacks must not hide geometry errors')

    def settle(self):
        for _ in range(5):
            self.root.update()

    def panel(self):
        content = theme.scrollable_card(self.root)
        canvas = content.master
        bars = {str(w.cget('orient')): w for w in canvas.master.winfo_children()
                if isinstance(w, ttk.Scrollbar)}
        return content, canvas, bars

    def test_all_palettes_use_one_main_surface_and_quiet_primary(self):
        style = ttk.Style(self.root)
        for mode in ('light', 'dark', 'ocean', 'forest', 'plum', 'system'):
            with self.subTest(mode=mode):
                palette = theme.palette_for(mode, system='dark')
                theme._apply_styles(self.root, palette)
                self.assertEqual(palette['surface'], palette['background'])
                for name in ('TFrame', 'DB.TFrame', 'DB.Card.TFrame', 'TLabel', 'DB.Heading.TLabel'):
                    self.assertEqual(style.lookup(name, 'background'), palette['background'])
                self.assertEqual(style.lookup('DB.Primary.TButton', 'background'), palette['surface_alt'])
                self.assertEqual(style.lookup('DB.Primary.TButton', 'foreground'), palette['text'])
                image = self.root._droidbridge_button_images['primary', 'normal']
                rgb = lambda color: tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                self.assertEqual(image.get(25, 25), rgb(palette['surface_alt']))
                self.assertEqual(image.get(0, 0), rgb(palette['background']))
                self.assertFalse(image.transparency_get(0, 0))
                self.assertEqual(len(self.root._droidbridge_button_images), 42)

    def test_normal_mapped_panel_has_no_scrollbars_when_content_fits(self):
        content, canvas, bars = self.panel()
        ttk.Label(content, text='Short settings page').pack(anchor='w')
        ttk.Button(content, text='Continue').pack(anchor='w')
        self.settle()
        self.assertTrue(canvas.winfo_ismapped())
        self.assertFalse(bars['vertical'].winfo_ismapped())
        self.assertFalse(bars['horizontal'].winfo_ismapped())
        self.assertEqual(int(canvas.cget('borderwidth')), 0)
        self.assertEqual(int(canvas.cget('highlightthickness')), 0)

    def test_vertical_overflow_is_visible_and_disappears_after_content_shrinks(self):
        content, canvas, bars = self.panel()
        rows = [ttk.Button(content, text=f'Action {i}') for i in range(25)]
        for row in rows:
            row.pack(anchor='w', pady=4)
        self.settle()
        self.assertTrue(bars['vertical'].winfo_ismapped())
        self.assertFalse(bars['horizontal'].winfo_ismapped())
        for row in rows[2:]:
            row.destroy()
        self.settle()
        self.assertFalse(bars['vertical'].winfo_ismapped())
        self.assertFalse(bars['horizontal'].winfo_ismapped())

    def test_unbreakable_content_gets_horizontal_scroll_only_when_needed(self):
        content, canvas, bars = self.panel()
        fixed = tk.Canvas(content, width=1500, height=80, borderwidth=0, highlightthickness=0)
        fixed.pack(anchor='w')
        self.settle()
        self.assertTrue(bars['horizontal'].winfo_ismapped())
        self.assertFalse(bars['vertical'].winfo_ismapped())
        self.assertGreater(content.winfo_width(), canvas.winfo_width())
        self.assertGreater(canvas.xview()[1] - canvas.xview()[0], 0)
        self.assertLess(canvas.xview()[1], 1)
        fixed.configure(width=200)
        self.settle()
        self.assertFalse(bars['horizontal'].winfo_ismapped())

    def test_high_dpi_long_labels_wrap_and_focus_reveals_last_action(self):
        self.root.tk.call('tk', 'scaling', 3)
        theme.apply_theme(self.root)
        self.root.geometry('620x420')
        content, canvas, bars = self.panel()
        label = ttk.Label(content, text='Long explanatory label with several words ' * 8)
        label.pack(fill='x')
        buttons = []
        for _ in range(7):
            button = ttk.Button(content, text='Continue configuring the remote connection with this computer')
            button.pack(anchor='w', pady=4)
            buttons.append(button)
        self.settle()
        self.assertTrue(bars['vertical'].winfo_ismapped())
        self.assertFalse(bars['horizontal'].winfo_ismapped())
        self.assertGreater(label.winfo_height(), font.Font(root=self.root, font=ttk.Style(self.root).lookup('TLabel', 'font')).metrics('linespace'))
        for button in buttons:
            self.assertGreater(len(str(button.cget('text')).splitlines()), 1)
            self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width())
        buttons[-1].focus_force()
        self.settle()
        self.assertGreaterEqual(buttons[-1].winfo_rooty(), canvas.winfo_rooty())
        self.assertLessEqual(buttons[-1].winfo_rooty() + buttons[-1].winfo_height(), canvas.winfo_rooty() + canvas.winfo_height())

    def test_live_palette_keeps_geometry_and_scroll_bindings_are_local(self):
        with tempfile.TemporaryDirectory() as data, patch.object(theme, 'system_theme', return_value='dark'):
            controller = theme.ThemeController(self.root, data)
            self.addCleanup(controller.dispose)
            content, canvas, bars = self.panel()
            ttk.Button(content, text='Continue', style='DB.Primary.TButton').pack()
            self.settle()
            before = self.root.bind_all('<MouseWheel>')
            for mode in ('ocean', 'forest', 'plum', 'light', 'dark'):
                controller.set_mode(mode)
                self.settle()
                self.assertFalse(bars['vertical'].winfo_ismapped())
                self.assertFalse(bars['horizontal'].winfo_ismapped())
                self.assertEqual(canvas.cget('background').lower(), controller.palette['background'].lower())
            self.assertEqual(self.root.bind_all('<MouseWheel>'), before)
            viewport = canvas.master
            viewport.destroy()
            self.assertFalse(self.root.bind('<MouseWheel>'))


if __name__ == '__main__':
    unittest.main()
