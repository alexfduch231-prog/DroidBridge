import hashlib
import tempfile
import unittest
from pathlib import Path
from file_outbox import Outbox, OutboxError, CHUNK_BYTES

class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Outbox(self.root/'data')
    def test_snapshot_survives_source_edit_and_restart(self):
        p=self.root/'source.txt';p.write_bytes(b'original')
        item=self.store.enqueue(p);p.write_bytes(b'changed')
        restored=Outbox(self.root/'data')
        self.assertEqual(b'original',restored.chunk(item['id'],0))
        self.assertEqual(hashlib.sha256(b'original').hexdigest(),item['sha256'])
        self.assertNotIn('path',item)
        self.assertEqual([item],restored.pending())
    def test_chunks_and_digest_required_to_ack(self):
        p=self.root/'source';p.write_bytes(b'x'*(CHUNK_BYTES+7))
        item=self.store.enqueue(p)
        self.assertEqual(CHUNK_BYTES,len(self.store.chunk(item['id'],0)))
        self.assertEqual(7,len(self.store.chunk(item['id'],CHUNK_BYTES)))
        with self.assertRaises(OutboxError):self.store.ack(item['id'],'0'*64)
        self.assertEqual(1,len(self.store.pending()))
        self.store.ack(item['id'],item['sha256']);self.assertEqual([],self.store.pending())
        self.store.ack(item['id'],item['sha256'])
    def test_paths_and_bad_offsets_rejected(self):
        for ident in ('../x','x','A'*32,'0'*33):
            with self.assertRaises(OutboxError):self.store.chunk(ident,0)
        p=self.root/'source';p.write_bytes(b'hello');item=self.store.enqueue(p)
        for offset in (-1,True,1,CHUNK_BYTES):
            with self.assertRaises(OutboxError):self.store.chunk(item['id'],offset)
    def test_missing_empty_and_symlink(self):
        with self.assertRaises(OutboxError):self.store.enqueue(self.root/'missing')
        p=self.root/'empty';p.touch();item=self.store.enqueue(p)
        self.assertEqual(b'',self.store.chunk(item['id'],0))
        self.assertEqual(0,item['size'])
    def test_expired_snapshots_are_removed_locally(self):
        from unittest.mock import patch
        import time
        p=self.root/'source';p.write_bytes(b'a');item=self.store.enqueue(p)
        with patch('file_outbox.time.time',return_value=time.time()+8*86400):
            self.store.cleanup()
        self.assertFalse((self.root/'data'/'file-outbox'/item['id']).exists())

    def test_staging_progress_and_cancellation_leave_no_snapshot(self):
        p=self.root/'large';p.write_bytes(b'x'*(CHUNK_BYTES+7))
        seen=[]
        item=self.store.enqueue(p,progress=lambda done,total:seen.append((done,total)))
        self.assertEqual((CHUNK_BYTES+7,CHUNK_BYTES+7),seen[-1])
        self.store.discard(item['id'])
        with self.assertRaises(OutboxError):
            self.store.enqueue(p,cancelled=lambda:True)
        self.assertEqual([],self.store.pending())
        self.assertEqual([],list(self.store.root.iterdir()))

    def test_staging_does_not_block_other_downloads(self):
        import threading
        p=self.root/'source';p.write_bytes(b'x')
        first=self.store.enqueue(p)
        reached=threading.Event();release=threading.Event()
        def progress(done,total):
            reached.set();release.wait(3)
        thread=threading.Thread(target=lambda:self.store.enqueue(p,progress=progress))
        thread.start();self.assertTrue(reached.wait(2))
        completed=threading.Event()
        reader=threading.Thread(target=lambda:(self.store.chunk(first['id'],0),completed.set()))
        reader.start()
        try:self.assertTrue(completed.wait(0.5),'Staging blocks existing downloads')
        finally:release.set();thread.join(5);reader.join(5)

    def test_corrupt_metadata_fails_closed(self):
        p=self.root/'source';p.write_bytes(b'a');item=self.store.enqueue(p)
        metadata=self.root/'data'/'file-outbox'/item['id']/'metadata.json'
        for invalid in ('[]', 'null', '{'):
            metadata.write_text(invalid)
            self.assertEqual([],self.store.pending())
        metadata.write_text('{')
        self.assertEqual([],self.store.pending())
        with self.assertRaises(OutboxError):self.store.chunk(item['id'],0)

if __name__=='__main__':unittest.main()
