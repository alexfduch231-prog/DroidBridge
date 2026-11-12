"""Offline discovery: one installation, bounded locations, no program execution."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from listener import media_tools


class MediaToolsDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'
        self.bundle = self.root / 'media'
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        # Never let an actual C:/ffmpeg installation affect an offline fixture.
        original_is_file = Path.is_file
        def fixture_is_file(path):
            if str(path).replace('\\', '/').lower().startswith('c:/ffmpeg/'):
                return False
            return original_is_file(path)
        files = patch.object(Path, 'is_file', fixture_is_file)
        files.start()
        self.addCleanup(files.stop)

    def pair(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        for name in ('ffmpeg.exe', 'ffplay.exe'):
            (folder / name).touch()
        return folder

    def discover(self):
        return media_tools.resolve_media_tools(self.data, media_dir=self.bundle)

    def test_distribution_wins_over_path_and_detected_installations(self):
        self.pair(self.bundle)
        local = self.root / 'local'
        self.pair(local / 'Programs' / 'FFmpeg' / 'bin')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
            with patch.object(media_tools.shutil, 'which', side_effect=AssertionError('PATH must not be needed')):
                tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools(str(self.bundle / 'ffmpeg.exe'),
                                                       str(self.bundle / 'ffplay.exe'), 'distribution'))

    def test_windows_path_pair_with_mocked_which_is_portable(self):
        with patch.object(media_tools.shutil, 'which', side_effect=lambda name: 'C:/tools/' + name + '.exe'):
            tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools('C:/tools/ffmpeg.exe', 'C:/tools/ffplay.exe', 'path'))

    def test_portable_path_names_without_exe_remain_supported(self):
        with patch.object(media_tools.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name):
            tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools('/usr/bin/ffmpeg', '/usr/bin/ffplay', 'path'))

    def test_split_path_installations_never_form_a_pair(self):
        with patch.object(media_tools.shutil, 'which', side_effect=lambda name: '/one/ffmpeg.exe' if name == 'ffmpeg' else '/two/ffplay.exe'):
            tools = self.discover()
        self.assertIsNone(tools.ffmpeg)
        self.assertIsNone(tools.ffplay)

    def test_single_path_tool_disables_both(self):
        for missing in ('ffmpeg', 'ffplay'):
            with self.subTest(missing=missing):
                with patch.object(media_tools.shutil, 'which', side_effect=lambda name: None if name == missing else '/tools/' + name):
                    tools = self.discover()
                self.assertIsNone(tools.ffmpeg)
                self.assertIsNone(tools.ffplay)

    def test_later_complete_path_directory_beats_detected_installation(self):
        first = self.root / 'first'
        first.mkdir()
        (first / 'ffmpeg.exe').touch()
        complete = self.pair(self.root / 'complete')
        local = self.root / 'local'
        self.pair(local / 'Programs' / 'FFmpeg' / 'bin')
        with patch.dict(os.environ, {'PATH': os.pathsep.join((str(first), str(complete))), 'LOCALAPPDATA': str(local)}):
            with patch.object(media_tools.shutil, 'which', side_effect=lambda name: str((first if name == 'ffmpeg' else complete) / (name + '.exe'))):
                tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools(str(complete / 'ffmpeg.exe'), str(complete / 'ffplay.exe'), 'path'))

    def test_detects_only_bounded_standard_environment_pairs_without_execution(self):
        locations = [('LOCALAPPDATA', ('Programs', 'FFmpeg', 'bin')),
                     ('LOCALAPPDATA', ('Microsoft', 'WinGet', 'Links')),
                     ('PROGRAMFILES', ('ffmpeg', 'bin')),
                     ('ChocolateyInstall', ('bin',))]
        for index, (variable, suffix) in enumerate(locations):
            with self.subTest(variable=variable, suffix=suffix):
                base = self.root / str(index)
                target = self.pair(base.joinpath(*suffix))
                with patch.dict(os.environ, {variable: str(base)}, clear=True):
                    with patch.object(media_tools.shutil, 'which', return_value=None):
                        with patch.object(media_tools.subprocess, 'run', side_effect=AssertionError('discovery must not execute')):
                            tools = self.discover()
                self.assertEqual(tools, media_tools.MediaTools(str(target / 'ffmpeg.exe'), str(target / 'ffplay.exe'), 'detected'))

    def test_incomplete_standard_directories_are_not_mixed(self):
        local, programs = self.root / 'local', self.root / 'programs'
        first = self.pair(local / 'Programs' / 'FFmpeg' / 'bin')
        second = self.pair(programs / 'ffmpeg' / 'bin')
        (first / 'ffplay.exe').unlink()
        (second / 'ffmpeg.exe').unlink()
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'PROGRAMFILES': str(programs)}):
            with patch.object(media_tools.shutil, 'which', return_value=None):
                tools = self.discover()
        self.assertIsNone(tools.ffmpeg)
        self.assertIsNone(tools.ffplay)

    def test_does_not_recurse_or_accept_relative_environment_paths(self):
        local = self.root / 'local'
        self.pair(local / 'Programs' / 'Other' / 'FFmpeg' / 'bin')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'PROGRAMFILES': 'relative'}):
            with patch.object(media_tools.shutil, 'which', return_value=None):
                with patch.object(Path, 'glob', side_effect=AssertionError('no scans')):
                    with patch.object(Path, 'rglob', side_effect=AssertionError('no scans')):
                        tools = self.discover()
        self.assertIsNone(tools.ffmpeg)
        self.assertIsNone(tools.ffplay)

    def test_invalid_explicit_configuration_blocks_all_fallbacks(self):
        self.pair(self.bundle)
        self.data.mkdir()
        settings = self.data / media_tools.SETTINGS_NAME
        for config in ('{broken', json.dumps({'version': 1, 'directory': str(self.root / 'missing')})):
            with self.subTest(config=config):
                settings.write_text(config, encoding='utf-8')
                with patch.object(media_tools.shutil, 'which', side_effect=AssertionError('must fail closed')):
                    with self.assertRaises(media_tools.MediaToolsError):
                        self.discover()

    def test_explicit_configuration_beats_bundled_pair(self):
        self.pair(self.bundle)
        selected = self.pair(self.root / 'selected')
        self.data.mkdir()
        (self.data / media_tools.SETTINGS_NAME).write_text(json.dumps({'version': 1, 'directory': str(selected)}), encoding='utf-8')
        tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools(str(selected / 'ffmpeg.exe'), str(selected / 'ffplay.exe'), 'configured'))

    def test_winget_links_to_different_installations_are_not_mixed(self):
        local = self.root / 'local'
        links = self.pair(local / 'Microsoft' / 'WinGet' / 'Links')
        original_resolve = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == links / 'ffmpeg.exe':
                return self.root / 'version-one' / 'ffmpeg.exe'
            if path == links / 'ffplay.exe':
                return self.root / 'version-two' / 'ffplay.exe'
            return original_resolve(path, *args, **kwargs)
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
            with patch.object(media_tools.shutil, 'which', return_value=None):
                with patch.object(Path, 'resolve', resolve):
                    tools = self.discover()
        self.assertIsNone(tools.ffmpeg)
        self.assertIsNone(tools.ffplay)

    @unittest.skipUnless(os.name == 'nt', 'fixed C: installation is Windows-only')
    def test_fixed_standard_windows_directory_is_inspected_without_a_scan(self):
        original_is_file = Path.is_file
        expected = Path('C:/ffmpeg/bin')
        def is_file(path):
            if path.parent == expected and path.name in ('ffmpeg.exe', 'ffplay.exe'):
                return True
            return original_is_file(path)
        with patch.object(media_tools.shutil, 'which', return_value=None):
            with patch.object(Path, 'is_file', is_file):
                with patch.object(media_tools.os, 'name', 'nt'):
                    tools = self.discover()
        self.assertEqual(tools, media_tools.MediaTools(str(expected / 'ffmpeg.exe'),
                                                       str(expected / 'ffplay.exe'), 'detected'))

    def test_path_wrappers_are_not_accepted_as_media_executables(self):
        with patch.object(media_tools.shutil, 'which', side_effect=lambda name: '/tools/' + name + '.cmd'):
            tools = self.discover()
        self.assertIsNone(tools.ffmpeg)
        self.assertIsNone(tools.ffplay)


if __name__ == '__main__':
    unittest.main()
