"""Real HTTP contract and crash-recovery tests for resumable uploads."""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / 'received'
        self.dest.mkdir()
        self.mod = importlib.import_module('resumable_upload')
        module = self.mod
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                module.handle_resumable(self)
            def send_bytes(self, status, content_type, body):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.token = 'secret'
        self.server.downloads_dir = self.dest
        self.server.upload_data_dir = self.root / 'state'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.id = 'a' * 32
        self.data = b'hello world'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, action, value=None, body=None, extra=None, token='secret'):
        headers = {'Authorization': 'Bearer ' + token}
        if body is None:
            body = json.dumps(value if value is not None else {'id': self.id}).encode()
        headers['Content-Length'] = str(len(body))
        headers.update(extra or {})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        conn.request('POST', '/upload/resume/' + action, body, headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def create(self, data=None, **kwargs):
        data = self.data if data is None else data
        value = {'id': self.id, 'name': 'Фото %2F.bin', 'size': len(data),
                 'sha256': hashlib.sha256(data).hexdigest()}
        value.update(kwargs)
        return self.request('create', value)

    def chunk(self, data=None, offset=0, **kwargs):
        data = self.data if data is None else data
        headers = {'X-Upload-Id': self.id, 'X-Upload-Offset': str(offset),
                   'X-Chunk-SHA256': hashlib.sha256(data).hexdigest()}
        headers.update(kwargs)
        return self.request('chunk', body=data, extra=headers)

    def test_create_idempotent_and_conflicting_identity(self):
        self.assertEqual(201, self.create()[0])
        self.assertEqual(200, self.create()[0])
        self.assertEqual(409, self.create(name='different')[0])

    def test_complete_unicode_percent_name_and_idempotent_finish(self):
        self.create()
        self.assertEqual(len(self.data), self.chunk()[1]['offset'])
        first = self.request('finish')
        self.assertEqual(200, first[0])
        self.assertTrue(first[1]['complete'])
        self.assertEqual('Фото %2F.bin', first[1]['name'])
        self.assertEqual(self.data, Path(first[1]['path']).read_bytes())
        self.assertEqual(first, self.request('finish'))
        self.assertEqual(first[1], self.create()[1])

    def test_auth_before_body_and_disk(self):
        status, _ = self.request('create', body=b'not json', token='wrong')
        self.assertEqual(403, status)
        self.assertFalse(self.server.upload_data_dir.exists())

    def test_boundaries_hash_and_offsets(self):
        self.create()
        self.assertEqual(409, self.chunk(offset=1)[0])
        self.assertEqual(409, self.chunk(**{'X-Chunk-SHA256': '0'*64})[0])
        self.assertEqual(0, self.request('status')[1]['offset'])
        self.assertEqual(409, self.request('finish')[0])
        self.assertEqual(413, self.request('chunk', body=b'', extra={'Content-Length': str(4194305)})[0])

    def test_invalid_names_ids_sizes_and_unknown_fields(self):
        for kwargs in ({'name':'../x'}, {'name':'CON.txt'}, {'id':'../x'}, {'size':True},
                       {'size':-1}, {'sha256':'x'}, {'directory':str(self.root)}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(400, self.create(**kwargs)[0])
        self.assertEqual(413, self.create(size=50*1024**3+1)[0])

    def test_json_and_http_limits(self):
        self.assertEqual(413, self.request('create', body=b' '*8193)[0])
        self.assertEqual(400, self.request('create', body=b'{')[0])
        self.assertEqual(400, self.request('status', extra={'Transfer-Encoding':'chunked'})[0])
        self.assertEqual(404, self.request('status')[0])

    def test_interrupted_chunk_rolls_back_and_restarts(self):
        self.create()
        sock = socket.create_connection(self.server.server_address)
        header = ('POST /upload/resume/chunk HTTP/1.1\r\nHost: localhost\r\n'
                  'Authorization: Bearer secret\r\nX-Upload-Id: '+self.id+'\r\n'
                  'X-Upload-Offset: 0\r\nX-Chunk-SHA256: '+hashlib.sha256(self.data).hexdigest()+'\r\n'
                  'Content-Length: '+str(len(self.data))+'\r\n\r\n').encode()
        sock.sendall(header + self.data[:3])
        sock.shutdown(socket.SHUT_WR)
        while sock.recv(4096):
            pass
        sock.close()
        importlib.reload(self.mod)
        self.assertEqual(0, self.request('status')[1]['offset'])
        self.assertEqual(200, self.chunk()[0])
        self.assertTrue(self.request('finish')[1]['complete'])

    def test_restart_truncates_uncommitted_tail(self):
        self.create()
        part = next(self.dest.glob('.pcmote-resume-*/data.part'))
        with part.open('ab') as stream:
            stream.write(b'uncommitted')
        importlib.reload(self.mod)
        self.assertEqual(0, self.request('status')[1]['offset'])
        self.assertEqual(0, part.stat().st_size)

    def test_destination_snapshot_and_collision(self):
        self.create()
        second = self.root / 'other'
        second.mkdir()
        self.server.downloads_dir = second
        (self.dest / 'Фото %2F.bin').write_bytes(b'original')
        self.chunk()
        result = self.request('finish')[1]
        self.assertEqual(self.dest, Path(result['path']).parent)
        self.assertEqual(b'original', (self.dest / 'Фото %2F.bin').read_bytes())
        self.assertEqual(self.data, Path(result['path']).read_bytes())

    def test_full_hash_mismatch_keeps_unpublished_session(self):
        self.create(sha256='0'*64)
        self.chunk()
        self.assertEqual(409, self.request('finish')[0])
        self.assertFalse((self.dest / 'Фото %2F.bin').exists())

    def test_abort_and_expiry_do_not_delete_destination(self):
        self.create()
        self.chunk()
        final = Path(self.request('finish')[1]['path'])
        self.assertEqual(200, self.request('abort')[0])
        self.assertTrue(final.exists())
        self.assertEqual(404, self.request('status')[0])
        self.id = 'b'*32
        self.create()
        with patch.object(self.mod.time, 'time', return_value=time.time()+8*86400):
            self.assertEqual(404, self.request('status')[0])

    def test_corrupt_index_fails_closed_without_touching_foreign_files(self):
        self.create()
        index = self.server.upload_data_dir / 'resumable-uploads' / (self.id+'.json')
        index.write_text('{"root":"'+str(self.root).replace('\\','\\\\')+'"}')
        self.assertEqual(500, self.request('status')[0])
        self.assertTrue(self.dest.exists())

    def test_symlink_part_rejected(self):
        self.create()
        part = next(self.dest.glob('.pcmote-resume-*/data.part'))
        foreign = self.root / 'foreign'
        foreign.write_bytes(b'private')
        part.unlink()
        try:
            part.symlink_to(foreign)
        except OSError:
            self.skipTest('Host does not allow symlinks')
        self.assertEqual(500, self.request('status')[0])
        self.assertEqual(b'private', foreign.read_bytes())

    def test_quota_and_disk_limits(self):
        with patch.object(self.mod, 'MAX_SESSIONS', 1):
            self.create()
            self.id = 'b'*32
            self.assertEqual(429, self.create()[0])
        with patch.object(self.mod.shutil, 'disk_usage') as usage:
            usage.return_value.free = 0
            self.assertEqual(507, self.create()[0])

    def test_create_crash_before_part_creation_can_retry(self):
        with patch.object(self.mod, '_recover', side_effect=OSError('simulated create crash')):
            self.assertEqual(500, self.create()[0])
        importlib.reload(self.mod)
        self.assertEqual(200, self.create()[0])
        self.assertEqual(200, self.chunk()[0])
        self.assertTrue(self.request('finish')[1]['complete'])

    def test_two_chunks_and_metadata_commit_failure_roll_back(self):
        data = b'x' * self.mod.CHUNK_BYTES + b'end'
        self.create(data=data)
        first = data[:self.mod.CHUNK_BYTES]
        with patch.object(self.mod, '_save', side_effect=OSError('commit failed')):
            self.assertEqual(500, self.chunk(data=first)[0])
        importlib.reload(self.mod)
        self.assertEqual(0, self.request('status')[1]['offset'])
        self.assertEqual(len(first), self.chunk(data=first)[1]['offset'])
        self.assertEqual(len(data), self.chunk(data=b'end', offset=len(first))[1]['offset'])
        self.assertTrue(self.request('finish')[1]['complete'])

    def test_unsupported_filesystem_rejected_before_create(self):
        with patch.object(self.mod.os, 'link', side_effect=OSError('unsupported')):
            status, result = self.create()
        self.assertEqual(500, status)
        self.assertIn('NTFS', result['error'])
        index = self.server.upload_data_dir / 'resumable-uploads' / (self.id+'.json')
        self.assertFalse(index.exists())
        self.assertEqual([], list(self.dest.iterdir()))

    def test_abort_retries_after_cleanup_crash_and_expiry_still_allows_create(self):
        self.create()
        self.chunk()
        part = next(self.dest.glob('.pcmote-resume-*/data.part'))
        part.unlink()
        part.parent.rmdir()
        self.assertEqual(200, self.request('abort')[0])
        self.assertEqual(404, self.request('status')[0])
        self.create()
        part = next(self.dest.glob('.pcmote-resume-*/data.part'))
        part.unlink()
        part.parent.rmdir()
        self.id = 'b'*32
        with patch.object(self.mod.time, 'time', return_value=time.time()+8*86400):
            self.assertEqual(201, self.create()[0])

    def test_existing_directory_is_a_collision_not_a_storage_failure(self):
        self.create(name='photos')
        (self.dest / 'photos').mkdir()
        self.chunk()
        status, result = self.request('finish')
        self.assertEqual(200, status)
        self.assertEqual('photos (1)', result['name'])
        self.assertTrue((self.dest / 'photos').is_dir())

    def test_maximum_name_collision_remains_recoverable(self):
        name = 'x'*176+'.bin'
        self.create(name=name)
        (self.dest / name).write_bytes(b'original')
        self.chunk()
        self.assertEqual(200, self.request('finish')[0])
        importlib.reload(self.mod)
        self.assertEqual(200, self.request('status')[0])
        self.assertEqual(200, self.request('abort')[0])
        self.id = 'b'*32
        self.assertEqual(201, self.create()[0])

    def test_reserved_bytes_follow_sessions_across_destination_change(self):
        self.create(size=1024*1024)
        other = self.root / 'second'
        other.mkdir()
        self.server.downloads_dir = other
        self.id = 'b'*32
        with patch.object(self.mod.shutil, 'disk_usage') as usage:
            usage.return_value.free = 16*1024**2 + 1024*1024
            self.assertEqual(507, self.create(size=1024*1024)[0])

    def test_empty_file(self):
        self.assertEqual(201, self.create(data=b'')[0])
        self.assertTrue(self.request('finish')[1]['complete'])

    def test_finish_crash_after_publish_recovers_same_file(self):
        self.create()
        self.chunk()
        original = self.mod._save
        def crash(index, state, token):
            if state.get('complete'):
                raise OSError('simulated crash after link')
            return original(index, state, token)
        with patch.object(self.mod, '_save', side_effect=crash):
            self.assertEqual(500, self.request('finish')[0])
        importlib.reload(self.mod)
        result = self.request('finish')
        self.assertEqual(200, result[0])
        self.assertEqual('Фото %2F.bin', result[1]['name'])
        self.assertEqual(1, len(list(self.dest.glob('*.bin'))))

    def test_concurrent_same_offset_only_commits_once(self):
        self.create()
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.chunk()[0])) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual([200,409], sorted(results))
        self.assertEqual(len(self.data), self.request('status')[1]['offset'])


if __name__ == '__main__':
    unittest.main()
