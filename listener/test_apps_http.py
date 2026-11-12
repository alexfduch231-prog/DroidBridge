import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('apps_listener', Path(__file__).with_name('pc-listener.py'))
listener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(listener)

class AppsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'apps.json'
        self.paths = patch.object(listener, 'APPS_FILE', str(self.path))
        self.paths.start()
        self.server = listener.Server(('127.0.0.1',0), listener.Handler)
        self.server.token = 'test-secret'
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.paths.stop(); self.tmp.cleanup()
    def get(self, key='test-secret'):
        c = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        c.request('GET','/apps?key='+key)
        r=c.getresponse(); status,body=r.status,r.read(); c.close()
        return status,body
    def test_auth_required(self):
        self.assertEqual(403,self.get('wrong')[0])
    def test_fresh_empty(self):
        status,body=self.get()
        self.assertEqual(200,status)
        self.assertEqual({'ok':True,'apps':[]},json.loads(body))
    def test_only_public_fields(self):
        self.path.write_text(json.dumps({'apps':[{'id':'demo','name':'Demo','path':'C:/private/app.exe','args':['private'],'task':'private','process':['app.exe']}]}),encoding='utf-8')
        status,body=self.get()
        self.assertEqual(200,status)
        self.assertEqual({'ok':True,'apps':[{'id':'demo','name':'Demo','can_close':True}]},json.loads(body))
        self.assertNotIn(b'private',body)
    def test_corrupt_fails_without_content_disclosure(self):
        self.path.write_text('private invalid config',encoding='utf-8')
        status,body=self.get()
        self.assertEqual(503,status)
        self.assertNotIn(b'private',body)

if __name__=='__main__': unittest.main()
