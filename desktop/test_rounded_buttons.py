"""Rounded rendering must not replace real ttk controls or leak on live updates."""
import gc
import tempfile
import tkinter as tk
import weakref
from tkinter import font, ttk
import unittest
from unittest.mock import patch

from desktop import theme


class RoundedButtonTests(unittest.TestCase):
    def root(self):
        root = tk.Tk()
        root.withdraw()  # Most contracts need no mapped native window.
        self.addCleanup(root.destroy)
        return root

    def test_buttons_use_nine_slice_images_and_keep_native_semantics(self):
        # A flat clam border or a Canvas substitute must fail this test.
        root = self.root()
        theme.apply_theme(root)
        style = ttk.Style(root)
        calls = []
        for name in ('TButton', 'DB.TButton', 'DB.Primary.TButton',
                     'DB.Danger.TButton', 'DB.Nav.TButton', 'DB.Nav.Selected.TButton',
                     'DB.Sidebar.TButton'):
            with self.subTest(style=name):
                button = ttk.Button(root, text='Continue', style=name,
                                    command=lambda: calls.append(True), takefocus=True)
                element = style.layout(name)[0][0]
                self.assertIn('Rounded', element)
                self.assertEqual(button.winfo_class(), 'TButton')
                self.assertIn('TButton', button.bindtags())
                self.assertTrue(button.bind_class('TButton', '<Key-space>'))
                self.assertTrue(style.layout(name)[0][1]['children'])
                button.invoke()
                button.state(['disabled'])
                button.invoke()
                self.assertEqual(len(calls), 1)
                calls.clear()
                self.assertTrue(button.cget('takefocus'))

    def test_live_presets_update_existing_images_without_unbounded_tcl_resources(self):
        # Recreating elements/images on each theme switch leaks and strands old widgets.
        root = self.root()
        with tempfile.TemporaryDirectory() as data, patch.object(theme, 'system_theme', return_value='light'):
            controller = theme.ThemeController(root, data)
            self.addCleanup(controller.dispose)
            button = ttk.Button(root, text='Existing', style='DB.Primary.TButton')
            images = root._droidbridge_button_images
            names = set(root.tk.call('image', 'names'))
            elements = set(ttk.Style(root).element_names())
            image = images['primary', 'normal']
            center = image.width() // 2
            for mode in ('light', 'dark', 'ocean', 'forest', 'plum', 'system') * 2:
                controller.set_mode(mode)
                self.assertEqual(set(root.tk.call('image', 'names')), names)
                self.assertEqual(set(ttk.Style(root).element_names()), elements)
                rgb = tuple(int(controller.palette['primary'][i:i+2], 16) for i in (1, 3, 5))
                self.assertEqual(image.get(center, center), rgb)
                self.assertFalse(image.transparency_get(0, 0))
                backdrop = tuple(int(controller.palette['surface'][i:i+2], 16) for i in (1, 3, 5))
                self.assertEqual(image.get(0, 0), backdrop)
                self.assertFalse(image.transparency_get(center, center))
                self.assertEqual(button.cget('style'), 'DB.Primary.TButton')
                ttk.Button(root, style='DB.Primary.TButton').destroy()
                self.assertNotEqual(images['primary', 'focus'].get(center, 1), image.get(center, 1))

    def test_root_isolation_and_state_precedence_include_focused_hover_and_press(self):
        first, second = self.root(), self.root()
        theme._apply_styles(first, theme.palette_for('light'))
        theme._apply_styles(second, theme.palette_for('light'))
        images = first._droidbridge_button_images
        self.assertIsNot(images, second._droidbridge_button_images)
        theme._apply_styles(first, theme.palette_for('ocean'))
        for root, expected in ((first, (23, 100, 155)), (second, (26, 99, 231))):
            image = root._droidbridge_button_images['primary', 'normal']
            self.assertEqual(image.get(image.width() // 2, image.height() // 2), expected)
        # Query the actual Tcl image element specification, not a parallel state table.
        # Tcl has no element introspection API, so capture its real creation call.
        third = self.root()
        original = ttk.Style.element_create
        with patch.object(ttk.Style, 'element_create', autospec=True,
                          side_effect=original) as create:
            theme.apply_theme(third)
        primary = next(call for call in create.call_args_list if call.args[1] == 'DB.Rounded.primary')
        specs = primary.args[4:]
        self.assertEqual([spec[:-1] for spec in specs], [
            ('disabled',), ('pressed', 'focus'), ('pressed',),
            ('active', 'focus'), ('active',), ('focus',)])
        self.assertEqual(primary.kwargs['sticky'], 'nsew')
        self.assertGreaterEqual(primary.kwargs['border'], 8)
        # Tk tiles rather than scales the center; tiny centers stall native paint.
        tile = third._droidbridge_button_images['primary', 'normal']
        self.assertGreaterEqual(tile.width() - 2 * primary.kwargs['border'], 24)
        self.assertEqual(primary.kwargs['padding'], 0)
        self.assertIn('DB.Rounded.primary', ttk.Style(first).element_names())
        self.assertNotEqual(str(images['primary', 'pressed_focus']), str(images['primary', 'pressed']))
        self.assertNotEqual(str(images['primary', 'active_focus']), str(images['primary', 'active']))

    def test_root_destroy_releases_photos_and_surviving_root_remains_valid(self):
        # A global PhotoImage cache would retain the destroyed interpreter/root.
        survivor = self.root()
        theme.apply_theme(survivor)
        root = tk.Tk()
        root.withdraw()
        theme.apply_theme(root)
        reference = weakref.ref(root._droidbridge_button_images['primary', 'normal'])
        root.destroy()
        del root
        gc.collect()
        self.assertIsNone(reference())
        theme._apply_styles(survivor, theme.palette_for('forest'))
        image = survivor._droidbridge_button_images['primary', 'normal']
        self.assertEqual(image.get(13, 13), (23, 107, 70))

    def test_all_theme_states_are_distinct_and_enabled_captions_have_contrast(self):
        # Dark presets used to reuse the resting accent for hover and press.
        def luminance(color):
            values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
            return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

        for mode in ('light', 'dark', 'ocean', 'forest', 'plum', 'system'):
            palette = theme.palette_for(mode, system='light')
            self.assertEqual(len({palette[key] for key in ('primary', 'primary_active', 'primary_pressed')}), 3)
            for key in ('primary', 'primary_active', 'primary_pressed',
                        'danger_button', 'danger_active', 'danger_pressed'):
                self.assertGreaterEqual(1.05 / (luminance(palette[key]) + .05), 4.5, (mode, key))

    def test_scrollable_card_wraps_caption_inside_scaled_native_label_parcel(self):
        from desktop.android_setup import show_android_setup
        root = self.root()
        previous = root.tk.call('tk', 'scaling')
        self.addCleanup(root.tk.call, 'tk', 'scaling', previous)
        root.tk.call('tk', 'scaling', 3)
        with tempfile.TemporaryDirectory() as data:
            window = show_android_setup(root, data, lambda: None)
            root.deiconify()  # A transient is unmapped while its owner is withdrawn.
            root.update()
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            buttons = [w for w in descendants(window) if isinstance(w, ttk.Button)]
            self.assertTrue(buttons)
            for button in buttons:
                face = font.Font(root=root, font=ttk.Style(root).lookup(button.cget('style') or 'TButton', 'font'))
                middle = button.winfo_height() // 2
                label_x = [x for x in range(button.winfo_width()) if button.identify(x, middle) == 'label']
                self.assertTrue(label_x, button.cget('text'))
                widest_line = max(face.measure(line) for line in str(button.cget('text')).splitlines())
                self.assertLessEqual(widest_line, len(label_x), button.cget('text'))
                self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width(), button.cget('text'))
            window.destroy()

    def test_padding_respects_scaling_without_fixed_height_or_text_clipping(self):
        root = self.root()
        # Tk scaling belongs to the display, not the individual interpreter.
        # Restore before root.destroy (cleanups run in reverse order).
        previous_scaling = root.tk.call('tk', 'scaling')
        self.addCleanup(root.tk.call, 'tk', 'scaling', previous_scaling)
        for scaling in (1.0, 4 / 3, 2.0, 3.0):
            root.tk.call('tk', 'scaling', scaling)
            theme.apply_theme(root)
            style = ttk.Style(root)
            button = ttk.Button(root, text='Продолжить подключение', style='DB.Primary.TButton')
            button.pack()
            root.update_idletasks()
            face = font.Font(root=root, font=style.lookup('TButton', 'font'))
            self.assertGreaterEqual(button.winfo_reqheight(), face.metrics('linespace') + 16)
            self.assertGreaterEqual(button.winfo_reqwidth(), face.measure(button.cget('text')) + 20)
            if scaling == 4 / 3:
                self.assertLessEqual(button.winfo_reqheight(), 48)
            self.assertLess(button.winfo_reqheight(), 130)
            button.destroy()


if __name__ == '__main__':
    unittest.main()
