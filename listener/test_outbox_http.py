import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from file_outbox import Outbox
spec=importlib.util.spec_from_file_location('outbox_listener',Path(__file__).with_name('pc-listener.py'))
listener=importlib.util.module_from_spec(spec);spec.loader.exec_module(listener)

class OutboxHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.server=listener.Server(('127.0.0.1',0),listener.Handler)
  self.server.token='test-only';self.server.upload_data_dir=self.root/'data'
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def post(self,route,payload,key='test-only'):
  c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
  c.request('POST','/outbox/'+route,json.dumps(payload),{'Authorization':'Bearer '+key})
  r=c.getresponse();result=r.status,r.read(),dict(r.getheaders());c.close();return result
 def test_authenticated_transfer(self):
  p=self.root/'private.txt';p.write_bytes(b'hello')
  item=Outbox(self.server.upload_data_dir).enqueue(p)
  status,body,_=self.post('list',{});self.assertEqual(200,status)
  self.assertEqual([item],json.loads(body)['files']);self.assertNotIn(str(self.root).encode(),body)
  status,body,headers=self.post('chunk',{'id':item['id'],'offset':0})
  self.assertEqual(200,status);self.assertEqual(b'hello',body);self.assertEqual(item['sha256'],headers['X-Chunk-SHA256'])
  self.assertEqual(200,self.post('ack',{'id':item['id'],'sha256':item['sha256']})[0])
  self.assertEqual([],json.loads(self.post('list',{})[1])['files'])
 def test_auth_and_path_injection(self):
  self.assertEqual(403,self.post('list',{},'wrong')[0])
  self.assertEqual(400,self.post('chunk',{'id':'../token.txt','offset':0})[0])
  self.assertEqual(400,self.post('list',{'path':'C:/private'})[0])
  self.assertEqual(400,self.post('enqueue',{'path':'C:/private'})[0])
 def test_resume_second_chunk_and_lost_ack_response_after_restart(self):
  from file_outbox import CHUNK_BYTES
  import hashlib
  content=b'a'*CHUNK_BYTES+b'final chunk'
  source=self.root/'resume.bin';source.write_bytes(content)
  item=Outbox(self.server.upload_data_dir).enqueue(source)
  status,first,_=self.post('chunk',{'id':item['id'],'offset':0})
  self.assertEqual(200,status);self.assertEqual(content[:CHUNK_BYTES],first)
  # A restarted HTTP service has no process-local session state to recover.
  self.server.shutdown();self.server.server_close();self.thread.join()
  self.server=listener.Server(('127.0.0.1',0),listener.Handler)
  self.server.token='test-only';self.server.upload_data_dir=self.root/'data'
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  status,second,headers=self.post('chunk',{'id':item['id'],'offset':CHUNK_BYTES})
  self.assertEqual(200,status);self.assertEqual(content[CHUNK_BYTES:],second)
  self.assertEqual(hashlib.sha256(first+second).hexdigest(),item['sha256'])
  self.assertEqual(hashlib.sha256(second).hexdigest(),headers['X-Chunk-SHA256'])
  self.assertEqual(200,self.post('ack',{'id':item['id'],'sha256':item['sha256']})[0])
  # Simulate a client that did not receive the ACK response and retries.
  self.assertEqual(200,self.post('ack',{'id':item['id'],'sha256':item['sha256']})[0])
  self.assertEqual([],json.loads(self.post('list',{})[1])['files'])
