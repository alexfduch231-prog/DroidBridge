"""Real Tk theme lifecycle and state-preserving appearance checks."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from desktop import theme


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)

    def test_frozen_selftest_explicitly_imports_appearance_modules(self):
        import ast
        source = (Path(__file__).parent / 'launcher.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Attribute) and node.test.attr == 'self_test')
        imported = {alias.name for node in ast.walk(branch) if isinstance(node, ast.Import)
                    for alias in node.names}
        self.assertIn('desktop.theme_settings', imported)
        self.assertIn('desktop.appearance_page', imported)
        components = next(node.value for node in ast.walk(branch) if isinstance(node, ast.Constant)
                          and node.value == 'appearance')
        self.assertEqual(components, 'appearance')

    def test_palette_presets_are_distinct_and_have_readable_text(self):
        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
        def contrast(a, b):
            x, y = sorted((luminance(a), luminance(b)))
            return (y + .05) / (x + .05)
        colors = set()
        for mode in ('light', 'dark', 'ocean', 'forest', 'plum'):
            palette = theme.palette_for(mode)
            colors.add(palette['background'])
            for surface in ('background', 'surface', 'surface_alt'):
                for text in ('text', 'muted', 'danger', 'success'):
                    self.assertGreaterEqual(contrast(palette[text], palette[surface]), 4.5, (mode, text, surface))
            for accent in ('primary', 'primary_active', 'primary_pressed', 'danger_button', 'danger_active', 'danger_pressed'):
                self.assertGreaterEqual(contrast(palette['button_text'], palette[accent]), 4.5, (mode, accent))
        self.assertEqual(len(colors), 5)

    def test_live_updates_existing_widgets_without_state_or_qr_changes(self):
        with patch.object(theme, 'system_theme', return_value='light'):
            controller = theme.ThemeController(self.root, self.data)
        reference = theme.PALETTE
        canvas = tk.Canvas(self.root, background=controller.palette['background'])
        entry = tk.Entry(self.root, background=controller.palette['surface'], foreground=controller.palette['text'])
        entry.insert(0, 'keep me')
        entry.configure(state='readonly')
        photo = tk.PhotoImage(master=self.root, width=2, height=2)
        photo.put('#ffffff', to=(0, 0, 2, 2))
        label = ttk.Label(self.root, image=photo, style='DB.QR.TLabel')
        qr_frame = tk.Label(self.root, image=photo, background='#FFFFFF')
        video = tk.Canvas(self.root, background='black')
        for mode in ('dark', 'ocean', 'forest', 'plum', 'light'):
            controller.set_mode(mode)
            self.assertIs(theme.PALETTE, reference)
            self.assertEqual(canvas.cget('background').lower(), controller.palette['background'].lower())
            self.assertEqual(entry.get(), 'keep me')
            self.assertEqual(entry.cget('state'), 'readonly')
            self.assertEqual(video.cget('background'), 'black')
            self.assertEqual(photo.get(0, 0), (255, 255, 255))
            self.assertEqual(qr_frame.cget('background'), '#FFFFFF')
            self.assertEqual(ttk.Style(self.root).lookup(label.cget('style'), 'background'), '#FFFFFF')

    def test_system_poll_and_custom_pinning_cancel_on_dispose(self):
        with patch.object(theme, 'system_theme', return_value='light') as detect:
            controller = theme.ThemeController(self.root, self.data)
            self.assertIs(theme.ThemeController(self.root, self.data), controller)
            detect.return_value = 'dark'
            controller._poll_system()
            self.assertEqual(controller.palette['background'], theme.palette_for('dark')['background'])
            controller.set_mode('forest')
            detect.reset_mock()
            controller._poll_system()
            detect.assert_not_called()
            self.assertEqual(controller.palette, theme.palette_for('forest'))
            controller.set_mode('system')
            timer = controller._timer
            self.assertIn(timer, self.root.tk.call('after', 'info'))
            controller.dispose()
            self.assertNotIn(timer, self.root.tk.call('after', 'info'))
            controller._poll_system()
            self.assertIsNone(controller._timer)

    def test_existing_treeview_uses_readable_preset_surfaces_and_selection(self):
        controller = theme.ThemeController(self.root, self.data)
        tree = ttk.Treeview(self.root, columns=('name',), show='headings')
        item = tree.insert('', 'end', values=('Keep this application',))
        tree.selection_set(item)
        style = ttk.Style(self.root)
        for mode in ('dark', 'ocean', 'forest', 'plum', 'light'):
            controller.set_mode(mode)
            self.assertEqual(style.lookup('Treeview', 'background'), controller.palette['surface_alt'])
            self.assertEqual(style.lookup('Treeview', 'fieldbackground'), controller.palette['surface_alt'])
            self.assertEqual(style.lookup('Treeview', 'foreground'), controller.palette['text'])
            self.assertEqual(style.lookup('Treeview', 'background', ('selected',)), controller.palette['primary'])
            self.assertEqual(style.lookup('Treeview', 'foreground', ('selected',)), controller.palette['button_text'])
            self.assertEqual(tree.item(item, 'values'), ('Keep this application',))
            self.assertEqual(tree.selection(), (item,))

    def test_destroy_cancels_timer_and_keeps_other_root_callbacks_alive(self):
        other = tk.Tk()
        controller = theme.ThemeController(other, self.data)
        timer = controller._timer
        other.destroy()
        self.assertTrue(controller._disposed)
        self.assertIsNone(controller._timer)
        self.assertNotIn(timer, self.root.tk.call('after', 'info'))
        controller._poll_system()
        self.assertIsNone(controller._timer)

    def test_preset_is_restored_and_events_are_local_to_root(self):
        from desktop.theme_settings import save_theme_mode
        save_theme_mode(self.data, 'ocean')
        controller = theme.ThemeController(self.root, self.data)
        self.assertEqual(controller.mode, 'ocean')
        self.assertIsNone(controller._timer)
        events = []
        self.root.bind('<<DroidBridgeThemeChanged>>', lambda event: events.append(event.widget), add='+')
        self.root.update()
        controller.set_mode('forest')
        self.assertEqual(events, [self.root])
        self.assertEqual(self.root.theme_controller.palette, theme.palette_for('forest'))

    def test_save_failure_does_not_change_selected_mode_or_palette(self):
        controller = theme.ThemeController(self.root, self.data)
        original = controller.palette.copy()
        with patch.object(theme, 'save_theme_mode', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                controller.set_mode('plum')
        self.assertEqual(controller.mode, 'system')
        self.assertEqual(controller.palette, original)

    def test_second_tk_root_does_not_inherit_first_root_theme(self):
        controller = theme.ThemeController(self.root, self.data)
        controller.set_mode('plum')
        other = tk.Tk()
        try:
            with patch.object(theme, 'system_theme', return_value='light'):
                theme.apply_theme(other)
            self.assertEqual(other.cget('background').lower(), '#f7f7f8')
            self.assertEqual(self.root.cget('background').lower(), theme.palette_for('plum')['background'].lower())
        finally:
            other.destroy()

    def test_settings_page_composes_media_and_forwards_disposal(self):
        from desktop.appearance_page import build_appearance_page
        controller = theme.ThemeController(self.root, self.data)
        media = ttk.Frame(self.root)
        disposed = []
        media.dispose = lambda: disposed.append(True)
        with patch('desktop.media_setup.build_media_page', return_value=media):
            page = build_appearance_page(self.root, self.data, controller)
        self.assertIs(page.media_page, media)
        page.mode_var.set('Океан')
        page.selector.event_generate('<<ComboboxSelected>>')
        self.root.update()
        self.assertEqual(controller.mode, 'ocean')
        page.dispose()
        self.assertEqual(disposed, [True])


if __name__ == '__main__':
    unittest.main()
