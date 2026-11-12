"""Icon tests never read the user's application catalog or launch applications."""
import concurrent.futures
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
import uuid
import shutil
from unittest.mock import patch

from PIL import Image
import app_icons


def png(color='red', size=(64, 64)):
    out = io.BytesIO()
    Image.new('RGBA', size, color).save(out, format='PNG')
    return out.getvalue()


def shortcut(target, icon=None):
    # A minimal Unicode Shell Link with a local LinkInfo and optional icon location.
    raw = str(target).encode('utf-16-le') + b'\0\0'
    info = struct.pack('<9I', 36 + len(raw), 36, 1, 0, 0, 0, 0, 36, 0) + raw
    flags = 2 | 128 | (64 if icon else 0)
    header = struct.pack('<I', 76) + bytes.fromhex('0114020000000000c000000000000046')
    header += struct.pack('<I', flags) + bytes(52)
    return header + info + (struct.pack('<H', len(str(icon))) + str(icon).encode('utf-16-le') if icon else b'')


class IconTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.catalog = self.root / 'catalog.json'
        self.exe = self.root / 'sample.exe'
        self.exe.write_bytes(b'synthetic')
        self.put(self.exe)
        self.calls = []
        def extract(path):
            self.calls.append(path)
            return png()
        self.extract = extract
        self.store = app_icons.IconCache(extractor=extract)

    def put(self, path, aid='demo'):
        self.catalog.write_text(json.dumps({'apps': [dict(id=aid, name='Synthetic', path=str(path))]}), encoding='utf-8')

    def test_new_arbitrary_ids_unicode_names_and_paths_have_no_predefined_app_dependency(self):
        from app_catalog import public_catalog, save_catalog
        apps = []
        colors = {}
        for number, name in enumerate(('Новый редактор 🧩', 'User tool 漢字', 'Unnamed vendor utility')):
            directory = self.root / ('fresh vendor %d' % number)
            directory.mkdir()
            path = directory / ('unlisted-' + uuid.uuid4().hex + '.EXE')
            path.write_bytes(b'synthetic executable fixture')
            aid = 'user-' + uuid.uuid4().hex
            apps.append(dict(id=aid, name=name, path=str(path)))
            colors[str(path)] = ('red', 'green', 'blue')[number]
        save_catalog(self.catalog, {'apps': apps})
        store = app_icons.IconCache(extractor=lambda source: png(colors[str(source)]))
        for number, entry in enumerate(public_catalog(self.catalog)):
            data = store.get(self.catalog, entry['id'])
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(((255, 0, 0, 255), (0, 128, 0, 255), (0, 0, 255, 255))[number], image.getpixel((32, 32)))
            self.assertEqual(apps[number]['name'], entry['name'])

    def test_new_catalog_item_and_existing_path_edit_refresh_without_restarting_cache(self):
        from app_catalog import save_catalog
        aid = 'first-' + uuid.uuid4().hex
        new_id = 'later-' + uuid.uuid4().hex
        replacement = self.root / ('replacement-' + uuid.uuid4().hex + '.exe')
        replacement.write_bytes(b'replacement fixture')
        store = app_icons.IconCache(extractor=lambda source: png('blue' if source == str(replacement) else 'red'))
        save_catalog(self.catalog, {'apps': [dict(id=aid, name='First user entry', path=str(self.exe))]})
        self.assertIsNotNone(store.get(self.catalog, aid))
        self.assertIsNone(store.get(self.catalog, new_id))
        save_catalog(self.catalog, {'apps': [dict(id=aid, name='Renamed user entry', path=str(replacement)), dict(id=new_id, name='New user entry', path=str(self.exe))]})
        with Image.open(io.BytesIO(store.get(self.catalog, aid))) as image:
            self.assertEqual((0, 0, 255, 255), image.getpixel((32, 32)))
        with Image.open(io.BytesIO(store.get(self.catalog, new_id))) as image:
            self.assertEqual((255, 0, 0, 255), image.getpixel((32, 32)))

    @unittest.skipUnless(os.name == 'nt', 'Windows shell only')
    def test_native_new_user_exe_and_generated_custom_shortcut_catalog(self):
        from app_catalog import save_catalog
        # Copy a known system binary under a random user-supplied filename.
        # It is inspected for its icon only: never launched or resolved by COM.
        user_exe = self.root / ('new-user-tool-' + uuid.uuid4().hex + '.exe')
        shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32' / 'notepad.exe', user_exe)
        custom = self.root / ('user-art-' + uuid.uuid4().hex + '.ico')
        Image.new('RGBA', (64, 64), (19, 173, 81, 255)).save(custom, format='ICO', sizes=[(64, 64)])
        link = self.root / ('my-custom-entry-' + uuid.uuid4().hex + '.lnk')
        link.write_bytes(shortcut(user_exe, custom))
        exe_id, link_id = 'exe-' + uuid.uuid4().hex, 'link-' + uuid.uuid4().hex
        save_catalog(self.catalog, {'apps': [dict(id=exe_id, name='Произвольная программа', path=str(user_exe)), dict(id=link_id, name='Свой ярлык 🎨', path=str(link))]})
        store = app_icons.IconCache()
        with patch('subprocess.Popen', side_effect=AssertionError('Icon lookup must not execute programs')), patch.object(os, 'startfile', side_effect=AssertionError('Icon lookup must not open files')):
            exe_png = store.get(self.catalog, exe_id)
            link_png = store.get(self.catalog, link_id)
        self.assertIsNotNone(exe_png)
        self.assertIsNotNone(link_png)
        self.assertLessEqual(len(exe_png), 65536)
        self.assertLessEqual(len(link_png), 65536)
        with Image.open(io.BytesIO(link_png)) as image:
            self.assertEqual((64, 64), image.size)
            self.assertEqual((19, 173, 81, 255), image.getpixel((32, 32)))

    def test_missing_icon_does_not_remove_user_entry_or_change_launch_metadata(self):
        from app_catalog import load_catalog, public_catalog, save_catalog
        aid = 'no-icon-' + uuid.uuid4().hex
        entry = dict(id=aid, name='User entry without icon', path=str(self.exe), args=['--synthetic'], cwd=str(self.root))
        save_catalog(self.catalog, {'apps': [entry]})
        before = self.catalog.read_bytes()
        self.assertIsNone(app_icons.IconCache(extractor=lambda source: None).get(self.catalog, aid))
        self.assertEqual([dict(id=aid, name='User entry without icon', can_close=False)], public_catalog(self.catalog))
        self.assertEqual(entry, load_catalog(self.catalog)['apps'][0])
        self.assertEqual(before, self.catalog.read_bytes())

    def test_id_only_missing_invalid_and_unknown_never_extract(self):
        for aid in ('', 'unknown', str(self.exe), '../sample.exe', 'a' * 129):
            self.assertIsNone(self.store.get(self.catalog, aid))
        self.assertEqual([], self.calls)

    def test_bounded_png_and_cache_invalidation(self):
        data = self.store.get(self.catalog, 'demo')
        self.assertEqual((64, 64), Image.open(io.BytesIO(data)).size)
        self.assertLessEqual(len(data), 65536)
        self.assertEqual(data, self.store.get(self.catalog, 'demo'))
        self.assertEqual(1, len(self.calls))
        self.exe.write_bytes(b'changed metadata')
        self.store.get(self.catalog, 'demo')
        self.assertEqual(2, len(self.calls))
        other = self.root / 'other.exe'; other.write_bytes(b'other')
        self.put(other)
        self.store.get(self.catalog, 'demo')
        self.assertEqual(3, len(self.calls))
        self.put(other, 'replacement')
        self.assertIsNone(self.store.get(self.catalog, 'demo'))

    def test_local_shortcut_without_custom_icon_extracts_only_exe(self):
        link = self.root / 'simple.lnk'; link.write_bytes(shortcut(self.exe))
        self.put(link)
        self.assertIsNotNone(self.store.get(self.catalog, 'demo'))
        self.assertEqual([str(self.exe)], self.calls)

    def test_catalog_error_or_deleted_source_is_generic_missing_icon(self):
        self.catalog.write_text('private invalid config', encoding='utf-8')
        self.assertIsNone(self.store.get(self.catalog, 'demo'))
        self.put(self.exe)
        self.exe.unlink()
        self.assertIsNone(self.store.get(self.catalog, 'demo'))
        self.assertEqual([], self.calls)

    def test_invalid_native_results_fall_back_without_disclosure(self):
        for result in (None, b'private invalid image', png(size=(128,128)), b'x' * 65537):
            store = app_icons.IconCache(extractor=lambda path: result)
            self.assertIsNone(store.get(self.catalog, 'demo'))
        def broken(path):
            raise OSError('private path')
        self.assertIsNone(app_icons.IconCache(extractor=broken).get(self.catalog, 'demo'))

    def test_network_and_non_executable_catalog_sources_are_not_extracted(self):
        for source in ('\\\\invalid.example\\share\\app.exe', '//invalid.example/share/app.exe', 'https://invalid.example/app.exe', str(self.root / 'bad.txt')):
            self.put(source)
            self.assertIsNone(self.store.get(self.catalog, 'demo'))
        self.assertEqual([], self.calls)

    def test_shortcut_uses_validated_custom_icon_without_shell_resolving_link(self):
        icon = self.root / 'custom.ico'; icon.write_bytes(b'icon')
        link = self.root / 'sample.lnk'; link.write_bytes(shortcut(self.exe, icon))
        self.put(link)
        self.assertIsNotNone(self.store.get(self.catalog, 'demo'))
        self.assertEqual([(str(icon), 0)], self.calls)
        self.exe.write_bytes(b'updated target')
        self.store.get(self.catalog, 'demo')
        icon.write_bytes(b'updated icon')
        self.store.get(self.catalog, 'demo')
        self.assertEqual(3, len(self.calls))
        link.write_bytes(shortcut('\\\\invalid.example\\share\\target.exe'))
        self.assertIsNone(self.store.get(self.catalog, 'demo'))
        self.assertEqual(3, len(self.calls))

    def test_cache_has_lru_bound_and_serializes_native_extraction(self):
        active = 0
        peak = 0
        guard = threading.Lock()
        def extract(path):
            nonlocal active, peak
            with guard:
                active += 1; peak = max(peak, active)
            time.sleep(.002)
            with guard:
                active -= 1
            return png()
        store = app_icons.IconCache(extractor=extract)
        apps = []
        for n in range(70):
            p = self.root / ('app%d.exe' % n); p.write_bytes(b'x')
            apps.append(dict(id='app%d' % n, name='Synthetic', path=str(p)))
        self.catalog.write_text(json.dumps({'apps': apps}), encoding='utf-8')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda n: store.get(self.catalog, 'app%d' % n), range(70)))
        self.assertTrue(all(results))
        self.assertEqual(1, peak)
        self.assertLessEqual(len(store._cache), 64)

    @unittest.skipUnless(os.name == 'nt', 'Windows shell only')
    def test_reparse_component_is_rejected_without_following(self):
        fake = self.root / 'junction'
        fake.mkdir()
        from types import SimpleNamespace
        real_lstat = os.lstat
        def lstat(path, *args, **kwargs):
            if os.path.normcase(str(path)) == os.path.normcase(str(fake)):
                return SimpleNamespace(st_file_attributes=0x400)
            return real_lstat(path, *args, **kwargs)
        with patch.object(app_icons.os, 'lstat', side_effect=lstat):
            with self.assertRaises(ValueError):
                app_icons._local(str(fake / 'sample.exe'))

    @unittest.skipUnless(os.name == 'nt', 'Windows shell only')
    def test_native_custom_resource_index(self):
        resource = Path(os.environ['SystemRoot']) / 'System32' / 'shell32.dll'
        data = app_icons.extract_icon((str(resource), 3))
        self.assertIsNotNone(data)
        self.assertEqual((64, 64), Image.open(io.BytesIO(data)).size)

    @unittest.skipUnless(os.name == 'nt', 'Windows shell only')
    def test_native_known_system_executable(self):
        system_exe = Path(os.environ['SystemRoot']) / 'System32' / 'notepad.exe'
        data = app_icons.extract_icon(str(system_exe))
        self.assertIsNotNone(data)
        self.assertLessEqual(len(data), 65536)
        image = Image.open(io.BytesIO(data)).convert('RGBA')
        self.assertEqual((64, 64), image.size)
        self.assertIsNotNone(image.getbbox())
        self.assertGreater(image.getchannel('A').getextrema()[1], 0)


class IconHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = Path(self.tmp.name) / 'catalog.json'
        exe = Path(self.tmp.name) / 'sample.exe'; exe.write_bytes(b'synthetic')
        self.catalog.write_text(json.dumps({'apps':[dict(id='demo', name='Synthetic', path=str(exe))]}), encoding='utf-8')
        spec = importlib.util.spec_from_file_location('icon_listener', Path(__file__).with_name('pc-listener.py'))
        self.listener = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.listener)
        self.path_patch = patch.object(self.listener, 'APPS_FILE', str(self.catalog)); self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.extraction = patch.object(app_icons, 'extract_icon', return_value=png()); self.extract = self.extraction.start()
        self.addCleanup(self.extraction.stop)
        self.server = self.listener.Server(('127.0.0.1', 0), self.listener.Handler)
        self.server.token = 'synthetic-token'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def get(self, query, key='synthetic-token'):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=4)
        conn.request('GET', '/app-icon' + query, headers={'Authorization':'Bearer ' + key})
        response = conn.getresponse(); result = response.status, response.getheader('Content-Type'), response.read(); conn.close()
        return result

    def test_auth_checked_before_catalog_or_extraction(self):
        self.assertEqual(403, self.get('?id=demo', key='wrong')[0])
        self.assertEqual(0, self.extract.call_count)

    def test_success_returns_only_png(self):
        status, mime, body = self.get('?id=demo')
        self.assertEqual((200, 'image/png'), (status, mime))
        self.assertEqual((64,64), Image.open(io.BytesIO(body)).size)
        self.assertNotIn(str(self.catalog.parent).encode(), body)

    def test_missing_unknown_path_and_duplicate_ids_return_generic_404(self):
        for query in ('', '?id=unknown', '?path=C:/private/app.exe', '?id=demo&id=other', '?id=../../private.exe'):
            status, mime, body = self.get(query)
            self.assertEqual(404, status)
            self.assertNotIn(b'private', body)
        self.assertEqual(0, self.extract.call_count)


if __name__ == '__main__':
    unittest.main()
