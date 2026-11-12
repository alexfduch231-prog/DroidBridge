"""Headless viewer UI checks: no module import, owner data, sockets or workers."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Widget:
    def __init__(self, parent=None, **options):
        self.parent = parent
        self.options = dict(options)
        self.children = []
        self.bindings = {}
        self.packing = {}
        if parent is not None:
            parent.children.append(self)

    def configure(self, **options):
        self.options.update(options)

    def cget(self, key):
        return self.options.get(key, '')

    def pack(self, **options):
        self.packing = options

    def place(self, **options):
        self.placement = options

    def bind(self, event, callback, add=None):
        self.bindings[event] = callback
        return event

    def winfo_children(self):
        return self.children

    def winfo_toplevel(self):
        return self.parent.winfo_toplevel() if self.parent else self

    def title(self, value):
        self.window_title = value

    def geometry(self, value):
        self.window_geometry = value

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


PALETTE = dict(background="#F1F3F8", surface="#FFFFFF", primary="#1A63E7",
               surface_alt="#EAF0FC", text="#16181D", muted="#5C6270",
               danger="#CC2F23", outline="#737B8B", line="#D8DEE9")


class ViewerThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path(__file__).with_name("pc-viewer.pyw").read_text(encoding="utf-8"))
        viewer = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Viewer")
        # Execute the actual UI method and color assignments only. Importing the
        # full module creates its data folder and probes external media tools.
        colors = [n for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id in
                          {"BG", "PANEL", "TEXT", "MUTED", "OK", "BAD", "PRIMARY"}
                          for t in n.targets)]
        from PIL import Image, ImageDraw
        cls.namespace = dict(Image=Image, ImageDraw=ImageDraw,
                             ImageTk=SimpleNamespace(PhotoImage=lambda image, master=None: image),
                             ttk=SimpleNamespace(Button=Widget), PALETTE=PALETTE, apply_theme=lambda root: None, font_family=lambda root: 'Segoe UI',
                             tk=SimpleNamespace(Frame=Widget, Label=Widget, Checkbutton=Widget,
                                                Button=Widget, Entry=Widget, BooleanVar=Variable))
        exec(compile(ast.Module(body=colors + [viewer], type_ignores=[]),
                     "pc-viewer.pyw", "exec"), cls.namespace)
        cls.Viewer = cls.namespace["Viewer"]

    def setUp(self):
        self.viewer = self.Viewer.__new__(self.Viewer)
        self.viewer.root = Widget()
        self.viewer.status = "подключение…"
        self.viewer.audio_enabled = True
        self.viewer.control_message = "управление выключено"
        self.viewer._build_ui()

    def descendants(self, widget=None):
        for child in (widget or self.viewer.root).children:
            yield child
            yield from self.descendants(child)

    def test_chrome_uses_light_palette_with_readable_status(self):
        self.assertEqual(self.viewer.root.options["bg"], "#F1F3F8")
        self.assertEqual(self.viewer.status_label.options["bg"], "#FFFFFF")
        self.assertEqual(self.viewer.status_label.options["fg"], "#5C6270")
        self.assertEqual(self.viewer.control_label.options["fg"], "#5C6270")

    def test_opt_in_controls_start_disabled_and_readable(self):
        self.assertFalse(self.viewer.control_var.get())
        for control in [self.viewer.control_toggle, *self.viewer.control_widgets]:
            with self.subTest(label=control.options.get("text", "entry")):
                self.assertEqual(control.options["state"], "disabled")
                if control is self.viewer.control_toggle or control is self.viewer.text_entry:
                    self.assertEqual(control.options.get("disabledforeground"), "#5C6270")
        self.assertEqual(self.viewer.text_entry.options.get("disabledbackground"), "#F1F3F8")

    def test_buttons_and_checkboxes_have_visible_keyboard_focus(self):
        controls = [self.viewer.control_toggle, *self.viewer.control_widgets]
        controls += [w for w in self.descendants() if "variable" in w.options and w.options.get("text") in ("Звук", "Поверх")]
        for control in controls:
            with self.subTest(label=control.options.get("text", "entry")):
                self.assertTrue(control.options.get("takefocus"))
                if "style" in control.options:
                    self.assertEqual(control.options["style"], "DB.Sidebar.TButton")
                else:
                    self.assertGreaterEqual(control.options.get("highlightthickness", 0), 1)
                    self.assertEqual(control.options.get("highlightcolor"), "#1A63E7")

    def test_checkmarks_are_dark_on_light_not_dark_on_dark(self):
        checks = [w for w in self.descendants() if "variable" in w.options]
        self.assertEqual(len(checks), 3)
        for check in checks:
            self.assertEqual(check.options["selectcolor"], PALETTE["surface_alt"])
            self.assertFalse(check.options["indicatoron"])
            self.assertIsNotNone(check.options["image"])
            self.assertEqual(check.options["fg"], "#16181D")

    def test_viewport_stays_black_and_window_geometry_unchanged(self):
        self.assertEqual(self.viewer.root.window_geometry, "480x960+1380+60")
        self.assertEqual(self.viewer.image_label.options,
                         dict(bg="#000000", bd=0, highlightthickness=0,
                              padx=0, pady=0, anchor="center"))
        self.assertEqual(self.viewer.viewport.packing,
                         dict(side="left", fill="both", expand=True, pady=8))
        self.assertEqual(self.viewer.image_label.placement['anchor'], 'nw')
        self.assertEqual(set(self.viewer.image_label.bindings),
                         {"<ButtonPress-1>", "<ButtonRelease-1>", "<Button-3>", "<MouseWheel>"})

    def test_ui_construction_preserves_local_callbacks_without_invoking_them(self):
        # __new__ provides no locks, queues or socket: any accidental control or
        # network execution during construction therefore fails this test.
        self.assertFalse(self.viewer.on_top.get())
        self.assertTrue(self.viewer.audio_var.get())
        self.assertEqual(self.viewer.control_toggle.options["command"], self.viewer._toggle_control)
        self.assertEqual(self.viewer.text_entry.bindings["<Return>"], self.viewer._send_text)
        self.assertEqual(self.viewer.root.bindings["<Configure>"], self.viewer._on_resize)
        self.assertEqual(len(self.viewer.control_widgets), 5)


class LiveViewerThemeTests(unittest.TestCase):
    """Real Tk widgets; only external networking/worker startup is blocked."""

    def setUp(self):
        import tkinter as tk
        import threading
        import socket
        from unittest.mock import patch
        from test_embedded_viewer import load_viewer
        self.module = load_viewer()
        self.root = tk.Tk()
        self.root.geometry("960x720+10+10")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.controller = SimpleNamespace(palette=dict(PALETTE))
        self.root.theme_controller = self.controller
        self.blockers = [patch.object(threading.Thread, "start"),
                         patch.object(socket, "create_connection", side_effect=AssertionError("network"))]
        for blocker in self.blockers:
            blocker.start()
        self.addCleanup(self.cleanup)
        self.root.update()

    def cleanup(self):
        for child in self.root.winfo_children():
            dispose = getattr(child, "dispose", None)
            if dispose:
                dispose()
        self.root.destroy()
        for blocker in reversed(self.blockers):
            blocker.stop()

    def page(self, parent=None):
        page = self.module.build_viewer_page(parent or self.root, "localhost", 8768, "test-token")
        page.pack(fill="both", expand=True)
        self.root.update()
        # Freeze asynchronous pumps: this test isolates a theme event while a
        # decoded frame and an outbound command are pending, not a frame render.
        for after_id in page.viewer._after_ids:
            page.after_cancel(after_id)
        page.viewer._after_ids.clear()
        return page

    def change(self, **colors):
        self.controller.palette.update(colors)
        self.root.event_generate("<<DroidBridgeThemeChanged>>")
        self.root.update()

    def test_root_palette_updates_existing_controls_without_touching_live_state(self):
        import time
        from unittest.mock import Mock
        viewer = self.page().viewer
        viewer.authenticated = viewer.control_capable = viewer.control_enabled = True
        viewer.last_rendered = time.monotonic()
        viewer._refresh_controls()
        viewer.text_entry.insert(0, "unsent text")
        decoder, photo, frame = Mock(), object(), object()
        viewer.vproc, viewer.photo, viewer.latest = decoder, photo, frame
        epoch, command = viewer.control_epoch, b"queued-command"
        viewer.control_q.put(command)
        for background, surface, text, muted, primary in (
                ("#111827", "#1F2937", "#F9FAFB", "#CBD5E1", "#93C5FD"),
                ("#081E2C", "#12344A", "#E5F5FF", "#B2D8F0", "#79D8FF"),
                ("#102519", "#1B3927", "#E9FBEF", "#BCD9C6", "#8DDFAC"),
                ("#28172B", "#402345", "#FFF0FF", "#DCC1E0", "#E6A6F2")):
            with self.subTest(background=background):
                self.change(background=background, surface=surface, text=text,
                            muted=muted, primary=primary, button_text="#FFFFFF")
                self.assertEqual(viewer.root.cget("bg"), background)
                self.assertEqual(viewer.status_label.cget("bg"), surface)
                self.assertEqual(viewer.status_label.cget("fg"), muted)
                self.assertEqual(viewer.control_label.cget("fg"), muted)
                self.assertEqual(viewer.control_toggle.cget("fg"), text)
                self.assertEqual(viewer.control_toggle.cget("selectcolor"), self.controller.palette["surface_alt"])
                self.assertEqual(viewer.text_entry.cget("insertbackground"), text)
                self.assertEqual(viewer.text_entry.cget("selectforeground"), "#FFFFFF")
                for widget in [viewer.control_toggle, viewer.text_entry]:
                    self.assertEqual(widget.cget("highlightcolor"), primary)
                    self.assertEqual(widget.cget("disabledforeground"), muted)
                for widget in viewer.control_widgets:
                    if widget is not viewer.text_entry:
                        self.assertEqual(widget.cget("style"), "DB.Sidebar.TButton")
                self.assertEqual(viewer.image_label.cget("bg"), "#000000")
                self.assertEqual(viewer.text_entry.get(), "unsent text")
                self.assertEqual(viewer.text_entry.cget("state"), "normal")
                self.assertTrue(viewer.control_var.get())
                self.assertIs(viewer.vproc, decoder)
                self.assertIs(viewer.photo, photo)
                self.assertIs(viewer.latest, frame)
                self.assertEqual(viewer.control_epoch, epoch)
                self.assertFalse(viewer.stop.is_set())
        self.assertIs(viewer.control_q.get_nowait(), command)
        decoder.kill.assert_not_called()
        viewer.vproc = None
        viewer.latest = None
        self.assertEqual(self.errors, [])

    def test_real_controller_modes_repaint_existing_viewer(self):
        import tempfile
        from desktop.theme import ThemeController, palette_for
        self.root.theme_controller = None
        with tempfile.TemporaryDirectory() as directory:
            controller = ThemeController(self.root, directory)
            try:
                viewer = self.page().viewer
                for mode in ("dark", "ocean", "forest", "plum", "light"):
                    with self.subTest(mode=mode):
                        controller.set_mode(mode)
                        self.root.update()
                        p = palette_for(mode)
                        self.assertEqual(viewer.root.cget("bg"), p["background"])
                        self.assertEqual(viewer.text_entry.cget("fg"), p["text"])
                        self.assertEqual(viewer.control_toggle.cget("selectcolor"), p["surface_alt"])
                        self.assertEqual(viewer.image_label.cget("bg"), "#000000")
                        viewer.status_color = self.module.BAD
                        viewer._pump()
                        self.assertEqual(viewer.status_label.cget("fg"), p["danger"])
                        for after_id in viewer._after_ids:
                            viewer.root.after_cancel(after_id)
                        viewer._after_ids.clear()
            finally:
                controller.dispose()

    def test_embedded_first_paint_uses_owning_root_not_global_light_palette(self):
        self.controller.palette.update(background="#111827", surface="#1F2937", text="#F9FAFB")
        viewer = self.page().viewer
        self.assertEqual(viewer.root.cget("bg"), "#111827")
        self.assertEqual(viewer.text_entry.cget("fg"), "#F9FAFB")
        self.module.apply_theme.assert_not_called()
        self.assertEqual(viewer.status_label.cget("font"), "{Segoe UI} 10")

    def test_standalone_reads_palette_installed_by_apply_theme(self):
        self.root.theme_controller = None
        def apply(root):
            root._droidbridge_palette = dict(PALETTE, background="#111827", text="#F9FAFB")
        self.module.apply_theme.side_effect = apply
        viewer = self.module.Viewer.__new__(self.module.Viewer)
        viewer.root = self.root
        viewer.status = "подключение…"
        viewer.audio_enabled = True
        viewer.control_message = "управление выключено"
        viewer._build_ui()
        self.assertEqual(self.root.cget("bg"), "#111827")
        self.assertEqual(viewer.text_entry.cget("fg"), "#F9FAFB")
        self.assertEqual(viewer.image_label.cget("bg"), "#000000")
        self.module.apply_theme.assert_called_once_with(self.root)

    def test_error_and_success_status_are_recolored_without_changing_status_identity(self):
        viewer = self.page().viewer
        viewer.status_color = self.module.BAD
        self.change(danger="#FFB4AB", success="#8EDBAA")
        self.assertEqual(viewer.status_label.cget("fg"), "#FFB4AB")
        self.assertEqual(viewer.status_color, self.module.BAD)
        viewer.status_color = self.module.OK
        self.change(success="#8EDBAA")
        self.assertEqual(viewer.status_label.cget("fg"), "#8EDBAA")

    def test_theme_listener_cleanup_preserves_other_root_callbacks(self):
        import tkinter as tk
        seen = []
        callback = self.root.bind("<<DroidBridgeThemeChanged>>", lambda event: seen.append(1), add="+")
        baseline = self.root.bind("<<DroidBridgeThemeChanged>>")
        container = tk.Frame(self.root)
        container.pack()
        page = self.page(container)
        self.assertNotEqual(self.root.bind("<<DroidBridgeThemeChanged>>"), baseline)
        self.change(background="#111827")
        self.assertEqual(page.cget("bg"), "#111827")
        page.dispose()
        page.dispose()
        self.assertEqual(self.root.bind("<<DroidBridgeThemeChanged>>").strip(), baseline.strip())
        self.change(background="#223344")
        self.assertEqual(len(seen), 2)
        self.root.unbind("<<DroidBridgeThemeChanged>>", callback)
        self.assertEqual(self.errors, [])

    def test_parent_destroy_removes_viewer_theme_listener(self):
        import tkinter as tk
        container = tk.Frame(self.root)
        baseline = self.root.bind("<<DroidBridgeThemeChanged>>")
        self.page(container)
        container.destroy()
        self.root.update()
        self.assertEqual(self.root.bind("<<DroidBridgeThemeChanged>>").strip(), baseline.strip())
        self.change(background="#111827")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
