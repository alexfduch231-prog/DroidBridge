"""Installed runtime data must never be written into bundled source files."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class DataPathsTests(unittest.TestCase):
    def test_listener_data_override(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'VZAIMOPULT_DATA_DIR': tmp}):
            spec=importlib.util.spec_from_file_location('listener_data_paths', Path(__file__).with_name('pc-listener.py'))
            mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            for name, filename in [('TOKEN_FILE','token.txt'),('APPS_FILE','apps.json'),('LOG_FILE','listener.log')]:
                self.assertEqual(Path(getattr(mod,name)),Path(tmp)/filename)

    def test_viewer_uses_data_override(self):
        source=(Path(__file__).parent.parent/'client/pc-viewer.pyw').read_text(encoding='utf-8')
        self.assertIn('VZAIMOPULT_DATA_DIR',source)
        self.assertIn('DATA_DIR',source)

if __name__=='__main__': unittest.main()
