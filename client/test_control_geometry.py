"""Headless control geometry/protocol tests; never starts the viewer."""
import json
import math
import unittest

try:
    from control_geometry import image_point, gesture_command, encode_control, control_allowed
except ImportError:
    image_point = gesture_command = encode_control = control_allowed = None


class GeometryTests(unittest.TestCase):
    def test_helpers_exist(self):
        self.assertTrue(callable(image_point), "normalized image hit-test is missing")

    def test_centered_portrait_rejects_side_bars(self):
        self.assertEqual(image_point(249.5, 249.5, 500, 500, 200, 400), (0.5, 0.5))
        self.assertIsNone(image_point(149, 250, 500, 500, 200, 400))
        self.assertIsNone(image_point(350, 250, 500, 500, 200, 400))

    def test_centered_landscape_and_pixel_edges(self):
        self.assertEqual(image_point(50, 150, 500, 500, 400, 200), (0.0, 0.0))
        self.assertEqual(image_point(449, 349, 500, 500, 400, 200), (1.0, 1.0))
        self.assertIsNone(image_point(250, 149, 500, 500, 400, 200))
        self.assertIsNone(image_point(250, 350, 500, 500, 400, 200))

    def test_invalid_geometry_and_nonfinite_rejected(self):
        for values in [(0, 0, 0, 5, 2, 2), (0, 0, 5, 5, 0, 2),
                       (math.nan, 0, 5, 5, 2, 2), (0, 0, 5, 5, 6, 2)]:
            self.assertIsNone(image_point(*values))

    def test_tap_longpress_swipe_classification(self):
        self.assertEqual(gesture_command((0.2, 0.3), (0.2, 0.3), 0.1, 0),
                         {"action": "tap", "x": 0.2, "y": 0.3})
        self.assertEqual(gesture_command((0.2, 0.3), (0.2, 0.3), 0.6, 2)["action"], "longpress")
        for elapsed, expected in [(0.001, 50), (0.3, 300), (10, 2000)]:
            result = gesture_command((0.2, 0.3), (0.8, 0.7), elapsed, 100)
            self.assertEqual(result, {"action": "swipe", "x": 0.2, "y": 0.3,
                                      "x2": 0.8, "y2": 0.7, "duration": expected})


class ValidationTests(unittest.TestCase):
    def test_control_requires_all_explicit_gates(self):
        self.assertTrue(control_allowed(True, True, True))
        for flags in [(False, True, True), (True, False, True), (True, True, False),
                      (True, "true", True), (True, 1, True)]:
            self.assertFalse(control_allowed(*flags))

    def test_valid_payloads_and_unicode_roundtrip(self):
        for cmd in [{"action": "tap", "x": 0, "y": 1},
                    {"action": "longpress", "x": 0.5, "y": 0.4},
                    {"action": "swipe", "x": 0, "y": 1, "x2": 1, "y2": 0, "duration": 50},
                    *[{"action": "global", "name": name} for name in
                      ("back", "home", "recents", "notifications")],
                    {"action": "text", "text": "Привет 👋"},
                    {"action": "text", "text": "😀" * 2000}]:
            payload = encode_control(cmd)
            self.assertLessEqual(len(payload), 8192)
            self.assertEqual(json.loads(payload.decode("utf-8")), cmd)

    def test_rejects_malformed_coordinates_actions_and_lengths(self):
        bad = [{"action": "tap", "x": x, "y": 0.5} for x in
               (-0.1, 1.1, math.nan, math.inf, True, "0.5", None)]
        bad += [{"action": "tap", "x": 0}, {"action": "root"},
                {"action": "tap", "x": 0, "y": 0, "extra": 1},
                {"action": "global", "name": "power"},
                {"action": "text", "text": "x" * 2001},
                {"action": "text", "text": 123},
                {"action": "text", "text": "\ud800"}, None]
        bad += [{"action": "swipe", "x": 0, "y": 0, "x2": 1, "y2": 1,
                 "duration": d} for d in (49, 2001, True, 100.5)]
        for cmd in bad:
            with self.subTest(command=repr(cmd)):
                with self.assertRaises(ValueError):
                    encode_control(cmd)


class ViewerControlTests(unittest.TestCase):
    """Exercise actual Viewer methods without importing Tk/Pillow or opening UI."""
    @classmethod
    def setUpClass(cls):
        import ast
        import hmac
        import pathlib
        import queue
        import struct
        import threading
        import time
        source = pathlib.Path(__file__).with_name("pc-viewer.pyw").read_text(encoding="utf-8")
        tree = ast.parse(source)
        viewer = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Viewer")
        ns = dict(queue=queue, struct=struct, threading=threading, time=time,
                  encode_control=encode_control, control_allowed=control_allowed,
                  TYPE_CONTROL=5, json=json, MUTED="muted", OK="ok", hmac=hmac,
                  log=lambda message: None)
        exec(compile(ast.Module(body=[viewer], type_ignores=[]), "pc-viewer.pyw", "exec"), ns)
        cls.Viewer = ns["Viewer"]

    def make_viewer(self):
        import queue
        import threading
        viewer = self.Viewer.__new__(self.Viewer)
        viewer.control_lock = threading.Lock()
        viewer.control_q = queue.Queue(maxsize=2)
        viewer.control_status_q = queue.Queue(maxsize=2)
        viewer.auto_control_pending = False
        viewer.control_epoch = 0
        viewer.connection_epoch = 0
        viewer.authenticated = viewer.control_capable = viewer.control_enabled = True
        viewer.sock = object()
        viewer.stop = threading.Event()
        import time
        viewer.last_rendered = time.monotonic()
        return viewer

    def test_queue_is_bounded_and_disconnect_invalidates(self):
        v = self.make_viewer()
        cmd = {"action": "global", "name": "back"}
        self.assertTrue(v._queue_control(cmd))
        self.assertTrue(v._queue_control(cmd))
        self.assertFalse(v._queue_control(cmd))
        old_epoch = v.control_epoch
        v._invalidate_connection(v.sock)
        self.assertTrue(v.control_q.empty())
        self.assertFalse(v.authenticated)
        self.assertFalse(v.control_enabled)
        self.assertIsNone(v.sock)
        self.assertFalse(v._queue_control(cmd, old_epoch))

    def test_each_gate_blocks_queue_and_stale_gestures(self):
        for attribute in ("authenticated", "control_capable", "control_enabled"):
            v = self.make_viewer()
            setattr(v, attribute, False)
            self.assertFalse(v._queue_control({"action": "global", "name": "home"}))
            self.assertTrue(v.control_q.empty())
        v = self.make_viewer()
        self.assertFalse(v._queue_control({"action": "global", "name": "home"}, -1))

    def test_hello_requires_token_and_explicit_boolean_capability(self):
        import queue
        for capability in (True, False, "true", 1, None):
            v = self.make_viewer()
            v.token = "secret"
            v.status_q = queue.Queue()
            v._on_hello(json.dumps({"token": "secret", "control": capability}).encode())
            self.assertTrue(v.authenticated)
            self.assertEqual(v.control_capable, capability is True)
            self.assertFalse(v.control_enabled)
        v = self.make_viewer()
        v.token = "secret"
        v.authenticated = False
        with self.assertRaises(ValueError):
            v._on_hello(b'{"token":"wrong","control":true}')
        self.assertFalse(v.authenticated)

    def handoff_viewer(self):
        import queue
        v = self.make_viewer()
        v.authenticated = v.control_capable = v.control_enabled = False
        v.auto_control_pending = True
        v.token = "secret"
        v.status_q = queue.Queue()
        v.last_rendered = 0.0
        return v

    def test_phone_handoff_auto_control_waits_for_valid_hello_and_fresh_frame(self):
        import time
        v = self.handoff_viewer()
        command = {"action": "global", "name": "back"}
        self.assertFalse(v._queue_control(command))
        with self.assertRaises(ValueError):
            v._on_hello(b'{"token":"wrong","control":true}')
        self.assertFalse(v.control_enabled)
        v._on_hello(b'{"token":"secret","control":true}')
        self.assertTrue(v.control_enabled)
        self.assertFalse(v._queue_control(command))
        v.last_rendered = time.monotonic()
        self.assertTrue(v._queue_control(command))
        v.last_rendered -= 2.0
        self.assertFalse(v._queue_control(command))

    def test_handoff_capability_must_be_boolean_and_intent_is_one_shot(self):
        for capability in (False, "true", 1, None):
            with self.subTest(capability=capability):
                v = self.handoff_viewer()
                v._on_hello(json.dumps({"token": "secret", "control": capability}).encode())
                self.assertFalse(v.control_enabled)
                v._on_hello(b'{"token":"secret","control":true}')
                self.assertFalse(v.control_enabled)

    def test_handoff_optout_and_reconnect_never_restore_control(self):
        from unittest.mock import Mock
        v = self.handoff_viewer()
        v._on_hello(b'{"token":"secret","control":true}')
        self.assertTrue(v.control_enabled)
        v.control_var = Mock()
        v.control_var.get.return_value = False
        v._toggle_control()
        self.assertFalse(v.control_enabled)
        v._on_hello(b'{"token":"secret","control":true}')
        self.assertFalse(v.control_enabled)
        v._invalidate_connection(v.sock)
        v.sock = object()
        v._on_hello(b'{"token":"secret","control":true}')
        self.assertFalse(v.control_enabled)

    def test_stopped_handoff_cannot_accept_late_hello(self):
        v = self.handoff_viewer()
        v.stop.set()
        v._invalidate_connection()
        v._on_hello(b'{"token":"secret","control":true}')
        self.assertFalse(v.authenticated)
        self.assertFalse(v.control_enabled)
        self.assertFalse(v.auto_control_pending)

    def test_serial_worker_drops_expired_command_before_fresh_one(self):
        import time
        v = self.make_viewer()
        sent = []
        class Socket:
            def sendall(self, data):
                sent.append(data)
                if len(sent) > 1 or data[5:] != b"expired":
                    v.stop.set()
        v.sock = Socket()
        v.control_q.put((v.sock, v.control_epoch, b"expired", time.monotonic() - 1.1))
        self.assertTrue(v._queue_control({"action": "global", "name": "home"}))
        v._control_loop()
        self.assertEqual(len(sent), 1)
        self.assertEqual(json.loads(sent[0][5:]), {"action": "global", "name": "home"})

    def test_stale_render_blocks_enqueue(self):
        import time
        v = self.make_viewer()
        v.last_rendered = time.monotonic() - 1.6
        self.assertFalse(v._queue_control({"action": "global", "name": "back"}))
        self.assertTrue(v.control_q.empty())

    def test_stale_render_blocks_worker_send(self):
        import queue
        import time
        v = self.make_viewer()
        sent = []
        class Socket:
            def sendall(self, data):
                sent.append(data)
        class Queue:
            def get(self, timeout):
                v.stop.set()
                return (v.sock, v.control_epoch, b"stale-frame", time.monotonic())
        v.sock = Socket()
        v.control_q = Queue()
        v.last_rendered = time.monotonic() - 1.6
        v._control_loop()
        self.assertEqual(sent, [])

    def test_queue_records_monotonic_enqueue_time(self):
        import time
        v = self.make_viewer()
        before = time.monotonic()
        self.assertTrue(v._queue_control({"action": "global", "name": "back"}))
        item = v.control_q.get_nowait()
        self.assertEqual(len(item), 4, "queued controls need an expiry timestamp")
        self.assertGreaterEqual(item[3], before)
        self.assertLessEqual(item[3], time.monotonic())

    def test_serial_worker_drops_old_epoch_then_sends_framed_json(self):
        import struct
        v = self.make_viewer()
        sent = []
        class Socket:
            def sendall(self, data):
                sent.append(data)
                v.stop.set()
        v.sock = Socket()
        import time
        v.control_q.put((v.sock, -1, b"stale", time.monotonic()))
        self.assertTrue(v._queue_control({"action": "tap", "x": 0.2, "y": 0.4}))
        v._control_loop()
        self.assertEqual(len(sent), 1)
        length, kind = struct.unpack(">IB", sent[0][:5])
        self.assertEqual(kind, 5)
        self.assertEqual(length, len(sent[0]) - 5)
        self.assertEqual(json.loads(sent[0][5:]), {"action": "tap", "x": 0.2, "y": 0.4})


if __name__ == "__main__":
    unittest.main()
