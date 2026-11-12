"""Local upload destination persistence; all data isolated in temporary folders."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from listener import upload_settings as settings


class UploadSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.downloads = self.root / 'Downloads'
        self.patch = patch.object(settings, 'downloads_folder', return_value=self.downloads)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.config = self.data / 'upload_settings.json'

    def test_default_downloads_can_be_created_without_writing_settings(self):
        self.assertEqual(settings.upload_directory(self.data), self.downloads)
        self.assertTrue(self.downloads.is_dir())
        self.assertFalse(self.config.exists())

    def test_existing_absolute_unicode_folder_roundtrips_and_preserves_other_data(self):
        folder = self.root / 'Приём файлов с телефона'
        folder.mkdir()
        for name in ('apps.json', 'token.txt'):
            (self.data / name).write_bytes(b'untouched')
        settings.save_upload_directory(self.data, folder)
        self.assertEqual(settings.upload_directory(self.data), folder)
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')), {'directory': str(folder)})
        for name in ('apps.json', 'token.txt'):
            self.assertEqual((self.data / name).read_bytes(), b'untouched')

    def test_invalid_selection_never_creates_custom_directory_or_settings(self):
        file = self.root / 'file'
        file.touch()
        for value in ('', 'relative', self.root / 'missing', file, None, 123):
            with self.subTest(value=value), self.assertRaises(settings.UploadSettingsError):
                settings.save_upload_directory(self.data, value)
        self.assertFalse((self.root / 'missing').exists())
        self.assertFalse(self.config.exists())

    def test_malformed_config_fails_closed_and_errors_do_not_leak_contents(self):
        for value in ('{private-secret', 'null', '[]', '{}', '{"directory": 1}',
                      '{"directory":"relative"}', '{"directory":"a","directory":"b"}',
                      '{"directory":"x","unexpected":true}'):
            self.config.write_text(value, encoding='utf-8')
            with self.subTest(value=value), self.assertRaises(settings.UploadSettingsError) as caught:
                settings.upload_directory(self.data)
            self.assertNotIn('private-secret', str(caught.exception))
            self.assertFalse(self.downloads.exists())

    def test_deleted_custom_directory_fails_without_recreation_or_fallback(self):
        folder = self.root / 'custom'
        folder.mkdir()
        settings.save_upload_directory(self.data, folder)
        folder.rmdir()
        with self.assertRaises(settings.UploadSettingsError):
            settings.upload_directory(self.data)
        self.assertFalse(folder.exists())
        self.assertFalse(self.downloads.exists())

    def test_oversized_or_deeply_nested_config_is_rejected_safely(self):
        for content in (' ' * 16385 + json.dumps({'directory': str(self.root)}),
                        '[' * 1500 + '0' + ']' * 1500):
            self.config.write_text(content, encoding='utf-8')
            with self.assertRaises(settings.UploadSettingsError):
                settings.upload_directory(self.data)
        self.assertFalse(self.downloads.exists())

    def test_unc_directory_is_rejected_even_when_reachable(self):
        with patch.object(Path, 'is_dir', return_value=True):
            with self.assertRaises(settings.UploadSettingsError):
                settings.save_upload_directory(self.data, '//server/share/receive')
        self.assertFalse(self.config.exists())

    def test_unreadable_config_fails_closed(self):
        self.config.mkdir()
        with self.assertRaises(settings.UploadSettingsError):
            settings.upload_directory(self.data)
        self.assertFalse(self.downloads.exists())

    def test_atomic_replace_failure_preserves_previous_settings_and_cleans_temp(self):
        first = self.root / 'first'
        second = self.root / 'second'
        first.mkdir()
        second.mkdir()
        settings.save_upload_directory(self.data, first)
        original = self.config.read_bytes()
        with patch.object(settings.os, 'replace', side_effect=OSError('private-path')):
            with self.assertRaises(settings.UploadSettingsError) as caught:
                settings.save_upload_directory(self.data, second)
        self.assertNotIn('private-path', str(caught.exception))
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(set(self.data.iterdir()), {self.config})

    def test_reset_recovers_corrupt_settings_and_uses_downloads(self):
        self.config.write_text('{broken', encoding='utf-8')
        settings.reset_upload_directory(self.data)
        self.assertFalse(self.config.exists())
        self.assertEqual(settings.upload_directory(self.data), self.downloads)

    def test_default_failure_is_sanitized(self):
        with patch.object(settings, 'downloads_folder', side_effect=OSError('private-default')):
            with self.assertRaises(settings.UploadSettingsError) as caught:
                settings.upload_directory(self.data)
        self.assertNotIn('private-default', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
