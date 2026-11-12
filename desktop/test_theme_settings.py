"""Bounded theme preferences and read-only Windows detection."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from desktop import theme_settings as settings


class ThemeSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)

    def test_default_and_invalid_preferences_are_system(self):
        self.assertEqual(settings.load_theme_mode(self.data), 'system')
        for payload in ('{', '[]', '{"schema":2,"mode":"dark"}',
                        '{"schema":true,"mode":"dark"}', '{"schema":1,"mode":"DARK"}',
                        '{"schema":1,"mode":{}}', 'x' * 8193):
            (self.data / 'theme_settings.json').write_text(payload, encoding='utf-8')
            self.assertEqual(settings.load_theme_mode(self.data), 'system')

    def test_every_preset_round_trips_with_schema_only(self):
        for mode in ('system', 'light', 'dark', 'ocean', 'forest', 'plum'):
            settings.save_theme_mode(self.data, mode)
            self.assertEqual(settings.load_theme_mode(self.data), mode)
            self.assertEqual(json.loads((self.data / 'theme_settings.json').read_text()),
                             {'schema': 1, 'mode': mode})
        with self.assertRaises(ValueError):
            settings.save_theme_mode(self.data, '#123456')

    def test_failed_atomic_replace_keeps_previous_settings_and_no_temp(self):
        settings.save_theme_mode(self.data, 'ocean')
        with patch.object(settings.os, 'replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError):
                settings.save_theme_mode(self.data, 'plum')
        self.assertEqual(settings.load_theme_mode(self.data), 'ocean')
        self.assertEqual([p.name for p in self.data.iterdir()], ['theme_settings.json'])

    def test_registry_detection_is_read_only_and_missing_falls_back(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        key = MagicMock()
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, KEY_READ=0x20019, REG_DWORD=4,
                                   OpenKey=MagicMock(return_value=key),
                                   QueryValueEx=MagicMock(return_value=(0, 4)))
        with patch.object(settings.sys, 'platform', 'win32'), patch.dict(sys.modules, winreg=registry):
            self.assertEqual(settings.system_theme(), 'dark')
            registry.OpenKey.assert_called_with(1,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize', 0, 0x20019)
            registry.QueryValueEx.return_value = (1, 4)
            self.assertEqual(settings.system_theme(), 'light')
            registry.OpenKey.side_effect = FileNotFoundError()
            self.assertEqual(settings.system_theme(), 'light')

    def test_non_windows_uses_light(self):
        with patch.object(settings.sys, 'platform', 'linux'):
            self.assertEqual(settings.system_theme(), 'light')


if __name__ == '__main__':
    unittest.main()
