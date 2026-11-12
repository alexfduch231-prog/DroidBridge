"""Catalog tests use temporary, synthetic data only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from listener import app_catalog as catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'apps.json'

    def put(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def app(self, **fields):
        return dict(id='sample', name='Sample', path='C:/Programs/sample.exe', **fields)

    def test_missing_is_empty_without_creating_file(self):
        self.assertEqual(catalog.load_catalog(self.path), {'apps': []})
        self.assertFalse(self.path.exists())

    def test_empty_file_is_not_silently_overwritten(self):
        self.path.write_bytes(b'')
        with self.assertRaises(catalog.CatalogError):
            catalog.load_catalog(self.path)

    def test_malformed_records_fail_closed(self):
        invalid = [[], {'apps': {}}, {'apps': [None]}, {'apps': [{}]},
                   {'apps': [self.app(args='--command')]},
                   {'apps': [self.app(process=['*.exe'])]},
                   {'apps': [dict(id='a', name='A', path='cmd.bat')]},
                   {'apps': [dict(id='a', name='A', path='https://host/app.exe')]},
                   {'apps': [dict(id='a', name='A', path='C:/a.exe\x00')]},
                   {'apps': [dict(id='a', name='\n', path='C:/a.exe')]}]
        for value in invalid:
            with self.subTest(value=value):
                self.put(value)
                with self.assertRaises(catalog.CatalogError):
                    catalog.load_catalog(self.path)

    def test_duplicate_ids_are_case_insensitive(self):
        self.put({'apps': [self.app(), dict(id='SAMPLE', name='Other', path='C:/b.exe')]})
        with self.assertRaises(catalog.CatalogError):
            catalog.load_catalog(self.path)

    def test_public_catalog_has_no_private_fields(self):
        self.put({'private': 'secret', 'apps': [self.app(args=['secret'], process=['sample.exe'],
                  task='private task', cwd='C:/private', future={'key': 'secret'})]})
        result = catalog.public_catalog(self.path)
        self.assertEqual(result, [{'id': 'sample', 'name': 'Sample', 'can_close': True}])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('C:/', json.dumps(result))

    def test_size_limit_and_sanitized_errors(self):
        self.path.write_bytes(b'x' * (catalog.MAX_CATALOG_BYTES + 1))
        with self.assertRaises(catalog.CatalogError) as error:
            catalog.load_catalog(self.path)
        self.assertLess(len(str(error.exception)), 200)
        self.path.write_text('{"private-token": invalid}', encoding='utf-8')
        with self.assertRaises(catalog.CatalogError) as error:
            catalog.load_catalog(self.path)
        self.assertNotIn('private-token', str(error.exception))

    def test_atomic_replace_failure_preserves_original_and_cleans_temp(self):
        original = {'apps': [self.app()]}
        self.put(original)
        with patch.object(catalog.os, 'replace', side_effect=OSError('private-token')):
            with self.assertRaises(catalog.CatalogError) as error:
                catalog.save_catalog(self.path, {'apps': []})
        self.assertNotIn('private-token', str(error.exception))
        self.assertEqual(catalog.load_catalog(self.path), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_save_round_trip_preserves_unknown_legacy_fields(self):
        value = {'version': 7, 'apps': [self.app(args=['--example'], cwd='C:/Programs',
                 process=['sample.exe'], task='Example Task', unknown={'nested': [1, 2]})]}
        catalog.save_catalog(self.path, value)
        self.assertEqual(catalog.load_catalog(self.path), value)

    def test_count_limit_matches_phone(self):
        apps = [dict(id='app%d' % index, name='Example', path='C:/example.exe')
                for index in range(101)]
        self.put({'apps': apps})
        with self.assertRaises(catalog.CatalogError):
            catalog.load_catalog(self.path)

    def test_public_payload_limit_rejects_instead_of_truncating(self):
        apps = [dict(id='app%d' % index, name='\U0001f600' * 200, path='C:/example.exe')
                for index in range(100)]
        self.put({'apps': apps})
        with self.assertRaises(catalog.CatalogError):
            catalog.public_catalog(self.path)

    def test_bom_and_shortcuts(self):
        self.path.write_text(json.dumps({'apps': [dict(id='x', name='X', path='C:/X.LNK')]}), encoding='utf-8-sig')
        self.assertFalse(catalog.public_catalog(self.path)[0]['can_close'])


if __name__ == '__main__':
    unittest.main()
