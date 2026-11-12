"""Headless local editor tests; no Tk windows and no processes are started."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import apps_panel
from listener.app_catalog import CatalogError, load_catalog


class AppsPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'apps.json'
        self.model = apps_panel.LocalAppsModel(self.directory)

    def executable(self, suffix='.exe'):
        path = self.directory / ('Example' + suffix)
        path.touch()
        return path

    def test_fresh_catalog_has_no_personalized_defaults(self):
        self.assertEqual(self.model.apps, [])
        self.assertFalse(self.path.exists())

    def test_add_requires_local_picker_and_supported_extension(self):
        for suffix in ('.exe', '.EXE', '.lnk'):
            with self.subTest(suffix=suffix):
                item = self.model.add_from_picker(self.executable(suffix), 'Example')
                self.assertEqual(item['name'], 'Example')
                self.assertTrue(Path(item['path']).is_absolute())
                self.assertNotIn('args', item)
                self.assertNotIn('process', item)
        for suffix in ('.bat', '.cmd', '.ps1', '.url', '.exe.bat'):
            with self.subTest(suffix=suffix):
                with self.assertRaises(CatalogError):
                    self.model.add_from_picker(self.executable(suffix), 'Bad')
        with self.assertRaises(CatalogError):
            self.model.add_from_picker(self.directory / 'missing.exe', 'Missing')

    def test_random_unique_stable_ids_and_rename(self):
        a = self.model.add_from_picker(self.executable(), 'A')
        b = self.model.add_from_picker(self.executable(), 'B')
        self.assertNotEqual(a['id'], b['id'])
        self.model.rename(a['id'], 'Renamed')
        self.assertEqual(load_catalog(self.path)['apps'][0]['id'], a['id'])
        self.assertEqual(load_catalog(self.path)['apps'][0]['name'], 'Renamed')

    def test_rename_and_remove_preserve_all_unknown_legacy_fields(self):
        legacy = {'revision': 42, 'apps': [{'id': 'legacy', 'name': 'Old',
                  'path': 'C:/legacy.exe', 'args': ['--local'], 'cwd': 'C:/',
                  'task': 'Legacy Task', 'process': ['legacy.exe'], 'extra': {'x': 1}}]}
        self.path.write_text(json.dumps(legacy), encoding='utf-8')
        model = apps_panel.LocalAppsModel(self.directory)
        model.rename('legacy', 'New')
        legacy['apps'][0]['name'] = 'New'
        self.assertEqual(load_catalog(self.path), legacy)
        model.remove('legacy')
        self.assertEqual(load_catalog(self.path), {'revision': 42, 'apps': []})

    def test_cancelled_picker_does_nothing(self):
        self.assertIsNone(self.model.add_from_picker('', 'Example'))
        self.assertFalse(self.path.exists())

    def test_save_failure_does_not_mutate_model(self):
        item = self.model.add_from_picker(self.executable(), 'Example')
        with patch.object(apps_panel, 'save_catalog', side_effect=CatalogError('Save failed')):
            with self.assertRaises(CatalogError):
                self.model.rename(item['id'], 'Unsaved')
        self.assertEqual(self.model.apps[0]['name'], 'Example')

    def test_local_changes_detect_conflicting_editor(self):
        self.model.add_from_picker(self.executable(), 'A')
        other = apps_panel.LocalAppsModel(self.directory)
        other.add_from_picker(self.executable(), 'B')
        with self.assertRaises(CatalogError):
            self.model.remove(self.model.apps[0]['id'])
        self.assertEqual(len(load_catalog(self.path)['apps']), 2)

    def test_invalid_names_and_unknown_ids_do_not_write(self):
        for name in ('', ' ', 'bad\nname', 'x' * 201):
            with self.assertRaises(CatalogError):
                self.model.add_from_picker(self.executable(), name)
        with self.assertRaises(CatalogError):
            self.model.rename('missing', 'Name')
        self.assertFalse(self.path.exists())

    def test_remote_mutation_is_explicitly_rejected(self):
        with self.assertRaises(PermissionError):
            self.model.add_from_picker(self.executable(), 'Remote', source='remote')
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
