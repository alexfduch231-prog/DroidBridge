"""Real Tk lifecycle checks, with all external workers and connections blocked."""
import ast
import json
import hmac
from control_geometry import control_allowed, encode_control
import os
import queue
import struct
import socket
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_viewer_theme import PALETTE


def load_viewer():
    # Avoid the module-level media-tool probe and user-data directory creation.
    tree = ast.parse(Path(__file__).with_name("pc-viewer.pyw").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if (isinstance(node, ast.ClassDef) and node.name == "Viewer")
             or (isinstance(node, ast.FunctionDef) and node.name == "build_viewer_page")]
    namespace = dict(tk=tk, threading=threading, queue=queue, socket=socket, time=time,
                     json=json, struct=struct, os=os, subprocess=subprocess,
                     hmac=hmac, control_allowed=control_allowed, encode_control=encode_control,
                     CREATE_NO_WINDOW=0x08000000, TYPE_HELLO=0, OK="#187645",
                     MEDIA_TOOLS=SimpleNamespace(ffplay=None, ffmpeg=None),
                     BG=PALETTE["background"], PANEL=PALETTE["surface"],
                     TEXT=PALETTE["text"], MUTED=PALETTE["muted"],
                     PRIMARY=PALETTE["primary"], BAD=PALETTE["danger"], PALETTE=PALETTE,
                     apply_theme=Mock(), log=lambda message: None)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pc-viewer.pyw", "exec"), namespace)
    return SimpleNamespace(**namespace)


class EmbeddedViewerTests(unittest.TestCase):
    def setUp(self):
        self.module = load_viewer()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest("Tk display unavailable: %s" % exc)
        self.root.geometry("960x720+10+10")
        self.root.title("Single shell")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.protocol = self.root.protocol("WM_DELETE_WINDOW")
        self.root.update()
        self.geometry = self.root.geometry()
        self.blockers = [patch.object(threading.Thread, "start"),
                         patch.object(socket, "create_connection", side_effect=AssertionError("real network"))]
        for blocker in self.blockers:
            blocker.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for page in list(self.root.winfo_children()):
            dispose = getattr(page, "dispose", None)
            if dispose:
                dispose()
        self.root.destroy()
        for blocker in reversed(self.blockers):
            blocker.stop()

    def page(self):
        page = self.module.build_viewer_page(self.root, "127.0.0.1", 8768, "test-token", audio=False)
        page.pack(fill="both", expand=True)
        self.root.update()
        return page

    def test_manual_page_does_not_auto_enable_after_capable_hello(self):
        viewer = self.page().viewer
        viewer._on_hello(b'{"token":"test-token","control":true}')
        viewer._refresh_controls()
        self.assertTrue(viewer.authenticated)
        self.assertFalse(viewer.control_enabled)
        self.assertFalse(viewer.control_var.get())

    def test_handoff_checkbox_tracks_authenticated_auto_control_and_optout(self):
        page = self.module.build_viewer_page(self.root, '127.0.0.1', 8768,
                                             'test-token', audio=False, auto_control=True)
        viewer = page.viewer
        self.assertFalse(viewer.control_enabled)
        viewer._on_hello(b'{"token":"test-token","control":true}')
        viewer._refresh_controls()
        self.assertTrue(viewer.control_var.get())
        viewer.control_toggle.invoke()
        self.assertFalse(viewer.control_enabled)
        viewer._refresh_controls()
        self.assertFalse(viewer.control_var.get())
        page.dispose()
        self.assertFalse(viewer.auto_control_pending)

    def test_embedding_keeps_single_shell_and_owns_only_frame(self):
        page = self.page()
        self.assertIsInstance(page, tk.Frame)
        self.assertIs(page.master, self.root)
        self.assertIs(page.viewer.root, page)
        self.assertFalse(any(isinstance(child, tk.Toplevel) for child in self.root.winfo_children()))
        self.assertEqual(self.root.title(), "Single shell")
        self.assertEqual(self.root.geometry(), self.geometry)
        self.assertEqual(self.root.protocol("WM_DELETE_WINDOW"), self.protocol)
        self.module.apply_theme.assert_not_called()
        self.assertEqual(page.viewer.image_label.cget("bg"), "#000000")
        self.assertEqual(page.cget("bg"), "#F1F3F8")
        self.assertGreater(page.viewer.image_label.winfo_height(), 100)
        self.assertGreater(page.viewer.image_label.winfo_width(), 100)

    def test_dispose_cancels_callbacks_invalidates_control_and_releases_resources(self):
        page = self.page()
        viewer = page.viewer
        sock, audio, decoder = Mock(), Mock(), Mock()
        viewer.sock, viewer.ffplay, viewer.vproc = sock, audio, decoder
        viewer.authenticated = viewer.control_capable = viewer.control_enabled = True
        viewer.last_rendered = time.monotonic()
        viewer.control_q.put((sock, viewer.control_epoch, b"stale", time.monotonic()))
        callbacks = set(self.root.tk.call("after", "info"))
        self.assertGreaterEqual(len(callbacks), 2)
        page.dispose()
        page.dispose()
        self.assertTrue(viewer.stop.is_set())
        self.assertFalse(viewer.authenticated)
        self.assertFalse(viewer.control_enabled)
        self.assertTrue(viewer.control_q.empty())
        self.assertIsNone(viewer.sock)
        self.assertIsNone(viewer.ffplay)
        self.assertIsNone(viewer.vproc)
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        sock.close.assert_called_once()
        audio.terminate.assert_called_once()
        decoder.kill.assert_called_once()
        self.assertFalse(page.winfo_exists())
        self.assertTrue(self.root.winfo_exists())
        self.assertFalse(callbacks.intersection(self.root.tk.call("after", "info")))
        # A previously dispatched callback must be harmless after disposal too.
        viewer._pump()
        viewer._tick()
        self.root.update()
        self.assertEqual(self.errors, [])

    def test_destroying_parent_disposes_embedded_workers_and_timers(self):
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)
        page = self.module.build_viewer_page(container, "localhost", 8768, "test-token")
        viewer = page.viewer
        container.destroy()
        self.root.update()
        self.assertTrue(viewer.stop.is_set())
        self.assertFalse(self.root.tk.call("after", "info"))
        self.assertEqual(self.errors, [])

    def test_embedded_stats_update_without_standalone_main(self):
        page = self.page()
        viewer = page.viewer
        viewer._stats_last = (time.monotonic() - 2.0, 0, 0)
        viewer.frames, viewer.bytes = 60, 4096
        viewer._tick()
        self.assertAlmostEqual(viewer.fps, 30.0, delta=1.0)
        self.assertAlmostEqual(viewer.kbps, 2.0, delta=0.1)
        self.assertIn("30 кадр/с", viewer._status_text())

    def test_connection_completed_after_dispose_is_closed_not_published(self):
        page = self.page()
        viewer = page.viewer
        sock = Mock()

        def finish_connect(*args, **kwargs):
            page.dispose()
            return sock

        with patch.object(socket, "create_connection", side_effect=finish_connect):
            viewer._net()
        self.assertIsNone(viewer.sock)
        sock.close.assert_called_once()
        sock.sendall.assert_not_called()
        self.assertFalse(viewer.authenticated)

    def test_disposed_viewer_cannot_restart_media_workers(self):
        page = self.page()
        viewer = page.viewer
        page.dispose()
        viewer.vw, viewer.vh = 1080, 1920
        viewer.audio_enabled = True
        with patch.dict(viewer._start_ffplay.__globals__, MEDIA_TOOLS=Mock()):
            # Without the stop gate, a non-path media tool leaks into os checks.
            viewer._start_ffplay()
        # No media-tool lookup or process start is allowed after disposal.
        self.assertIsNone(viewer._ensure_decoder())
        viewer._start_ffplay()
        self.assertIsNone(viewer.ffplay)
        self.assertIsNone(viewer.vproc)

    def test_dispose_stops_process_before_closing_possibly_blocked_writer(self):
        page = self.page()
        viewer = page.viewer
        events = []
        viewer.ffplay, viewer.vproc = Mock(), Mock()
        viewer.ffplay.terminate.side_effect = lambda: events.append("audio-stop")
        viewer.ffplay.stdin.close.side_effect = lambda: events.append("audio-pipe")
        viewer.vproc.kill.side_effect = lambda: events.append("video-stop")
        viewer.vproc.stdin.close.side_effect = lambda: events.append("video-pipe")
        page.dispose()
        self.assertLess(events.index("audio-stop"), events.index("audio-pipe"))
        self.assertLess(events.index("video-stop"), events.index("video-pipe"))

    def test_blocked_decoder_config_write_does_not_hold_dispose_lock(self):
        page = self.page()
        viewer = page.viewer
        viewer.vw, viewer.vh, viewer.h264_config = 1080, 1920, b"config"
        entered, released = threading.Event(), threading.Event()
        outcomes = []
        proc = Mock()

        def write_config(data):
            entered.set()
            released.wait(2.0)  # Fail boundedly even if production holds vlock.

        proc.stdin.write.side_effect = write_config
        proc.kill.side_effect = released.set
        worker = threading.Thread(target=lambda: outcomes.append(viewer._ensure_decoder()))
        with patch.dict(viewer._ensure_decoder.__globals__,
                        MEDIA_TOOLS=SimpleNamespace(ffmpeg=__file__, ffplay=None)), \
                patch.object(subprocess, "Popen", return_value=proc):
            # Start this one fault-injection worker, not the viewer workers.
            self.blockers[0].stop()
            with patch.object(viewer, "_read_stderr"):
                worker.start()
                self.assertTrue(entered.wait(1.0))
                began = time.monotonic()
                page.dispose()
                elapsed = time.monotonic() - began
                worker.join(1.0)
            self.blockers[0].start()
        self.assertLess(elapsed, 0.5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes, [None])

    def test_standalone_still_configures_window_and_close_destroys_it(self):
        viewer = self.module.Viewer(self.root, "localhost", 8768, "test-token", audio=False)
        self.assertEqual(self.root.title(), "Экран телефона — DroidBridge")
        self.module.apply_theme.assert_called_once_with(self.root)
        self.assertNotEqual(self.root.protocol("WM_DELETE_WINDOW"), self.protocol)
        viewer.close()
        # Replace the destroyed test root so common cleanup remains valid.
        self.root = tk.Tk()
        self.root.withdraw()


if __name__ == "__main__":
    unittest.main()
