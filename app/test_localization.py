"""Offline localization contracts; run python -B -m unittest discover -s app -v."""
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).parent

def strings(folder):
    result = {}
    for file in (ROOT / 'res' / folder).glob('*.xml'):
        for node in ET.parse(file).getroot().findall('string'):
            if node.get('name') in result:
                raise AssertionError('Duplicate string: ' + node.get('name'))
            result[node.get('name')] = ''.join(node.itertext())
    return result

class LocalizationTests(unittest.TestCase):
    def test_english_complete_and_format_contracts(self):
        ru, en = strings('values'), strings('values-en')
        self.assertTrue(en, 'English resources are missing')
        self.assertEqual(set(ru), set(en))
        for name, text in ru.items():
            with self.subTest(name=name):
                self.assertEqual(sorted(re.findall(r'%(?:\d+\$)?[dsf]', text)),
                                 sorted(re.findall(r'%(?:\d+\$)?[dsf]', en[name])))
                self.assertTrue(en[name].strip())
                self.assertFalse(re.search('[А-Яа-я]', en[name]), 'Untranslated English resource')

    def test_locale_lifecycle_and_release(self):
        src = ROOT / 'src/ru/alexv/pcmote'
        helper = src / 'AppLocale.java'
        self.assertTrue(helper.exists(), 'Shared locale context is missing')
        locale = helper.read_text(encoding='utf-8')
        self.assertIn('createConfigurationContext', locale)
        self.assertIn('setLocale', locale)
        self.assertIn('putString', locale)
        for name in ('MainActivity', 'ScreenActivity', 'MirrorService'):
            self.assertIn('AppLocale.wrap', (src / (name + '.java')).read_text(encoding='utf-8'))
        main = (src / 'MainActivity.java').read_text(encoding='utf-8')
        self.assertIn('AppLocale.select', main)
        self.assertIn('recreate()', main)
        for file in (ROOT / 'res/layout').glob('*.xml'):
            for node in ET.parse(file).getroot().iter():
                for attribute in ('text', 'hint', 'contentDescription'):
                    value = node.get('{http://schemas.android.com/apk/res/android}' + attribute, '')
                    self.assertFalse(re.search('[А-Яа-я]', value), str(file.name) + ': hardcoded UI text')
        manifest = (ROOT / 'AndroidManifest.xml').read_text(encoding='utf-8')
        self.assertIn('android:versionCode="31"', manifest)
        self.assertIn('android:versionName="1.21"', manifest)

if __name__ == '__main__':
    unittest.main(verbosity=2)
