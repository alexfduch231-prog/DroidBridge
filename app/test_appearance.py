"""Theme resource contracts shared with the Windows palette."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parent

class AppearanceTests(unittest.TestCase):
    def test_presets_match_windows_backgrounds(self):
        path = APP / 'res/values/appearance.xml'
        self.assertTrue(path.exists(), 'six-mode appearance resource is missing')
        root = ET.parse(path).getroot()
        styles = {s.attrib['name']: {i.attrib['name']: i.text for i in s} for s in root.findall('style')}
        for name, color in [('Light','#F7F7F8'),('Dark','#1B1B1B'),('Ocean','#081D30'),('Forest','#10231C'),('Plum','#24152F')]:
            self.assertEqual(color, styles['Appearance.'+name]['db_bg_screen'])
            self.assertEqual(color, styles['Appearance.'+name]['db_surface'])

    def test_selector_colors_are_shapes_not_unresolved_drawable_attributes(self):
        for path in (APP/'res/drawable').glob('*.xml'):
            for node in ET.parse(path).getroot().iter():
                self.assertFalse(node.get('{http://schemas.android.com/apk/res/android}drawable','').startswith('?attr/'),str(path))

    def test_resource_drawables_use_theme_roles(self):
        offenders = []
        for folder in ['drawable','color']:
            for path in (APP/'res'/folder).glob('*.xml'):
                if '@color/bg_screen' in path.read_text(encoding='utf-8'):
                    offenders.append(path.name)
        self.assertEqual([], offenders, 'fixed resource colors bypass selected palette')

if __name__ == '__main__': unittest.main()
