import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]

class BrandingTests(unittest.TestCase):
    def test_visible_brand(self):
        for locale in ('values', 'values-en'):
            strings = ET.parse(ROOT / 'app/res' / locale / 'strings.xml').getroot()
            values = {x.get('name'): x.text for x in strings}
            self.assertEqual('PConDistance', values['app_name'])
            self.assertFalse(any('DroidBridge' in (x.text or '') for x in strings))
        launcher = (ROOT / 'desktop/launcher.py').read_text(encoding='utf-8')
        self.assertIn("root.title('PConDistance')", launcher)
        installer = (ROOT / 'packaging/installer.iss').read_text(encoding='utf-8')
        self.assertIn('AppName=PConDistance', installer)

    def test_upgrade_identities_unchanged(self):
        manifest = ET.parse(ROOT / 'app/AndroidManifest.xml').getroot()
        self.assertEqual('ru.alexv.pcmote', manifest.get('package'))
        protocol = (ROOT / 'desktop/update_protocol.py').read_text(encoding='utf-8')
        self.assertIn("REPOSITORY = 'alexfduch231-prog/DroidBridge'", protocol)
        self.assertIn('DroidBridge/update-manifest/v1', protocol)
        installer = (ROOT / 'packaging/installer.iss').read_text(encoding='utf-8')
        self.assertIn('C4DA7A3E-0382-4A31-A965-D81455D35B1E', installer)
        self.assertIn('Programs\\DroidBridge', installer)
        self.assertIn('DroidBridge.exe', installer)

if __name__ == '__main__': unittest.main()
