"""Offline native-button resource contracts; not an on-device rendering test."""
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).parent
A = '{http://schemas.android.com/apk/res/android}'


def styles(folder='values'):
    return {s.get('name'): s for s in ET.parse(ROOT / 'res' / folder / 'styles.xml').getroot().findall('style')}


def items(style):
    return {n.get('name'): n.text for n in style.findall('item')}


def resolved(name):
    if name not in styles():
        raise AssertionError('Missing common button style: ' + name)
    node = styles()[name]
    result = resolved(node.get('parent')) if node.get('parent') in styles() else {}
    result.update(items(node))
    return result


class ButtonTests(unittest.TestCase):
    def test_day_night_programmatic_and_app_dialog_defaults(self):
        for folder in ('values', 'values-night'):
            theme = styles(folder)
            self.assertEqual(items(theme['AppTheme']).get('android:buttonStyle'), '@style/AppButton')
            self.assertEqual(items(theme['AppTheme']).get('android:alertDialogTheme'), '@style/AppDialogTheme')
            self.assertEqual(items(theme['AppDialogTheme']).get('android:buttonBarButtonStyle'), '@style/BtnDialog')
            self.assertIn('Dialog.Alert', theme['AppDialogTheme'].get('parent'))
        self.assertEqual(items(styles()['ScreenTheme']).get('android:buttonStyle'), '@style/BtnToolbar')

    def test_common_styles_clear_platform_gray_tint_and_elevation(self):
        for name in ('AppButton', 'BtnFilled', 'BtnOutline', 'BtnDanger', 'BtnWake', 'BtnDialog', 'BtnToolbar'):
            with self.subTest(style=name):
                values = resolved(name)
                self.assertEqual(values.get('android:backgroundTint'), '@null')
                self.assertEqual(values.get('android:stateListAnimator'), '@null')
                self.assertGreaterEqual(int(values['android:minHeight'][:-2]), 48)
                self.assertEqual(values.get('android:textAllCaps'), 'false')
                self.assertTrue(values['android:textColor'].startswith('@color/button_'))

    def test_app_owned_buttons_are_covered_without_default_or_gray_overrides(self):
        count = 0
        for file in (ROOT / 'src').rglob('*.java'):
            text = file.read_text(encoding='utf-8')
            for match in re.finditer(r'new\s+Button\(([^;]+?)\)', text):
                count += 1
                # One-argument native Buttons inherit AppTheme/ScreenTheme buttonStyle.
                args = match.group(1).replace(' ', '')
                self.assertTrue(args in ('this', 'activity') or 'R.style.Btn' in args, str(file))
        self.assertEqual(count, 9, 'Review newly added programmatic buttons for themed context')
        desktop = (ROOT / 'src/ru/alexv/pcmote/DesktopControl.java').read_text(encoding='utf-8')
        pairing = (ROOT / 'src/ru/alexv/pcmote/PairingActivity.java').read_text(encoding='utf-8')
        self.assertIn('new Button(activity, null, 0, R.style.BtnToolbar)', desktop)
        self.assertIn('new Button(this, null, 0, R.style.BtnFilled)', pairing)
        for file in (ROOT / 'res/layout').glob('*.xml'):
            for node in ET.parse(file).getroot().iter('Button'):
                style = node.get('style', '@style/AppButton').split('/')[-1]
                self.assertIn(style, styles())
                self.assertIsNone(node.get(A + 'backgroundTint'), str(file))
                if node.get(A + 'id', '').startswith('@+id/nav_'):
                    # Preserve the reviewed drawer's selected/ripple presentation.
                    self.assertEqual(node.get(A + 'background'), '@drawable/nav_item')
                    self.assertEqual(node.get(A + 'textColor'), '?attr/db_text_primary')
                else:
                    self.assertIsNone(node.get(A + 'background'), str(file))
                    self.assertIsNone(node.get(A + 'textColor'), str(file))
                self.assertGreaterEqual(int(node.get(A + 'minWidth', '48dp')[:-2]), 48, str(file))
                height = node.get(A + 'layout_height', 'wrap_content')
                if height.endswith('dp'):
                    self.assertGreaterEqual(int(height[:-2]), 48, str(file))

    def test_ripple_disabled_focus_and_moderate_rounding(self):
        for name in ('btn_filled', 'btn_outline', 'btn_danger', 'btn_wake', 'btn_flat', 'btn_toolbar'):
            root = ET.parse(ROOT / 'res/drawable' / (name + '.xml')).getroot()
            self.assertEqual(root.tag, 'ripple', name)
            self.assertTrue(any(n.get(A + 'state_enabled') == 'false' for n in root.iter('item')), name)
            self.assertTrue(any(n.get(A + 'state_focused') == 'true' for n in root.iter('item')), name)
            self.assertTrue(any(n.get(A + 'state_pressed') == 'true' for n in root.iter('item')), name)
            for corner in root.iter('corners'):
                self.assertLessEqual(int(corner.get(A + 'radius')[:-2]), 16)
        self.assertIn('@drawable/btn_danger', items(styles()['BtnDanger']).values())
        self.assertIn('@drawable/btn_wake', items(styles()['BtnWake']).values())

    def test_enabled_text_contrast_day_night_and_video(self):
        def luminance(value):
            rgb = value[-6:]
            channels = [int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
            return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722)))
        for folder in ('values', 'values-night'):
            colors = {n.get('name'): n.text for n in ET.parse(ROOT / 'res' / folder / 'colors.xml').getroot() if n.tag == 'color'}
            for fg, bg in (('on_primary', 'primary'), ('on_danger', 'danger'), ('primary', 'surface'),
                           ('primary', 'bg_screen'), ('wake_text', 'wake_bg_top'), ('wake_text', 'wake_bg_bottom'),
                           ('button_toolbar_text', 'button_toolbar_surface')):
                self.assertIn(fg, colors, 'Missing button palette role: ' + fg)
                self.assertIn(bg, colors, 'Missing button palette role: ' + bg)
                light, dark = sorted((luminance(colors[fg]), luminance(colors[bg])), reverse=True)
                self.assertGreaterEqual((light + .05) / (dark + .05), 4.5, folder + ': ' + fg + '/' + bg)
        screen = ET.parse(ROOT / 'res/layout/screen_view.xml').getroot()
        for node in screen.iter('Button'):
            self.assertEqual(node.get('style'), '@style/BtnToolbar')
            self.assertIsNone(node.get(A + 'background'))
            self.assertIsNone(node.get(A + 'textColor'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
