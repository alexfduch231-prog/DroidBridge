"""Local-only mirror handoff: real files, no sockets or GUI required."""
import importlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


class MirrorHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.h = importlib.import_module('desktop.mirror_handoff')
        self.gui = self.h.GuiMirrorHandoff(self.data)
        self.addCleanup(self.gui.close)

    def publish(self, **changes):
        payload = dict(nonce='a' * 32, owner=self.gui.owner, host='192.168.1.3', port=8768, created=time.time())
        payload.update(changes)
        path = self.data / 'mirror-request.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        path.chmod(0o600)
        return path

    def test_request_requires_main_gui_and_never_spawns(self):
        self.assertEqual(self.h.request_mirror(self.data, '192.168.1.3', 8768), (False, 'Открой главное окно PConDistance'))
        self.assertFalse((self.data / 'mirror-request.json').exists())

    def test_roundtrip_only_latest_and_consume_once_no_token(self):
        self.assertTrue(self.gui.heartbeat())
        self.assertTrue(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])
        self.assertTrue(self.h.request_mirror(self.data, '192.168.1.4', 8769)[0])
        payload = json.loads((self.data / 'mirror-request.json').read_text())
        self.assertEqual(set(payload), {'nonce', 'owner', 'host', 'port', 'created'})
        req = self.gui.consume()
        self.assertEqual((req.host, req.port), ('192.168.1.4', 8769))
        self.assertIsNone(self.gui.consume())

    def test_invalid_and_out_of_range_addresses_rejected(self):
        self.gui.heartbeat()
        for host, port in [('hostname', 8768), ('127.0.0.1;cmd', 8768), ('192.168.1.3', 0), ('192.168.1.3', 65536), ('192.168.1.3', True)]:
            with self.subTest(host=host, port=port):
                self.assertFalse(self.h.request_mirror(self.data, host, port)[0])

    def test_invalid_messages_deleted_and_never_consumed(self):
        for changes in [dict(host='example.com'), dict(port=0), dict(port=True), dict(created=time.time()-11), dict(created=time.time()+1), dict(created=float('nan')), dict(nonce='x'), dict(owner='b'*32), dict(command='run'), dict(created=True)]:
            with self.subTest(changes=changes):
                path = self.publish(**changes)
                self.assertIsNone(self.gui.consume())
                self.assertFalse(path.exists())

    def test_replayed_nonce_rejected(self):
        self.publish()
        self.assertIsNotNone(self.gui.consume())
        self.publish()
        self.assertIsNone(self.gui.consume())

    def test_malformed_and_oversize_are_removed(self):
        for body in ['{', '[]', 'x'*5000, '['*500 + ']'*500, '['*1024, '{"owner":"a","owner":"b"}']:
            path = self.data / 'mirror-request.json'
            path.write_text(body)
            path.chmod(0o600)
            self.assertIsNone(self.gui.consume())
            self.assertFalse(path.exists())

    def test_stale_or_future_heartbeat_rejected(self):
        self.gui.heartbeat()
        path = self.data / 'mirror-gui-heartbeat.json'
        original = json.loads(path.read_text())
        for created in [time.time()-11, time.time()+1, float('inf')]:
            path.write_text(json.dumps(dict(original, created=created)))
            self.assertFalse(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])

    def test_old_gui_close_does_not_remove_new_gui_heartbeat(self):
        self.gui.heartbeat()
        other = self.h.GuiMirrorHandoff(self.data)
        self.addCleanup(other.close)
        other.heartbeat()
        self.gui.close()
        self.assertTrue(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])
        self.assertIsNotNone(other.consume())

    def test_old_owner_request_not_delivered_to_new_gui(self):
        self.gui.heartbeat()
        self.h.request_mirror(self.data, '192.168.1.3', 8768)
        other = self.h.GuiMirrorHandoff(self.data)
        self.addCleanup(other.close)
        other.heartbeat()
        self.assertIsNone(other.consume())

    def test_symlink_never_followed(self):
        target = self.data / 'outside'
        target.write_text('private target')
        path = self.data / 'mirror-request.json'
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest('OS does not permit symlink creation')
        self.assertIsNone(self.gui.consume())
        self.assertEqual(target.read_text(), 'private target')
        self.assertTrue(self.gui.heartbeat())
        self.assertFalse(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])

    def test_parser_recursion_limit_is_fail_closed(self):
        self.publish()
        with patch.object(self.h.json, 'loads', side_effect=RecursionError('nested input')):
            self.assertIsNone(self.gui.consume())
            self.assertFalse(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])

    def test_failed_private_acl_does_not_publish_or_leave_temporary_files(self):
        with patch.object(self.h, '_private_windows', side_effect=OSError('ACL unavailable')):
            self.assertFalse(self.gui.heartbeat())
        self.assertEqual(list(self.data.iterdir()), [])

    def test_atomic_failure_preserves_previous_request(self):
        self.gui.heartbeat()
        self.h.request_mirror(self.data, '192.168.1.3', 8768)
        before = (self.data / 'mirror-request.json').read_bytes()
        with patch.object(self.h.os, 'replace', side_effect=OSError('replace failed')):
            self.assertFalse(self.h.request_mirror(self.data, '192.168.1.4', 8768)[0])
        self.assertEqual((self.data / 'mirror-request.json').read_bytes(), before)
        self.assertEqual(len(list(self.data.iterdir())), 2)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows DACL verification')
    def test_published_files_have_protected_owner_and_system_only_dacl(self):
        import ctypes
        from ctypes import wintypes
        self.assertTrue(self.gui.heartbeat())
        self.assertTrue(self.h.request_mirror(self.data, '192.168.1.3', 8768)[0])
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        get = advapi.GetFileSecurityW
        get.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        get.restype = wintypes.BOOL
        convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD)]
        convert.restype = wintypes.BOOL
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        for name in ['mirror-request.json', 'mirror-gui-heartbeat.json']:
            size = wintypes.DWORD()
            get(str(self.data / name), 4, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            self.assertTrue(get(str(self.data / name), 4, buffer, size.value, ctypes.byref(size)))
            text = wintypes.LPWSTR()
            self.assertTrue(convert(buffer, 1, 4, ctypes.byref(text), None))
            try:
                self.assertEqual(text.value, 'D:P(A;;FA;;;SY)(A;;FA;;;OW)')
            finally:
                kernel.LocalFree(text)

    def test_runtime_dispatch_hands_off_without_viewer_process(self):
        runtime = importlib.import_module('desktop.runtime')
        class Module:
            @staticmethod
            def main():
                if Module.client_alive():
                    return True, 'stale viewer pid skipped handoff'
                return Module.start_mirror_client('192.168.1.3', 8768)
            @staticmethod
            def client_alive():
                return True  # An unrelated/stale standalone viewer must not suppress GUI requests.
        self.gui.heartbeat()
        with patch.object(runtime, 'data_directory', return_value=self.data), patch.object(runtime, 'load_component', return_value=Module), patch.object(runtime, 'create_update_signal', return_value=None), patch.object(runtime, 'start_child') as spawn, patch.object(runtime.sys, 'argv', ['runtime']):
            self.assertEqual(runtime.run_component('server', []), (True, ''))
            spawn.assert_not_called()
        self.assertIsNotNone(self.gui.consume())


if __name__ == '__main__':
    unittest.main()
