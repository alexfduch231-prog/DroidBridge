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

    def pack(self, **options):
        self.packing = options

    def bind(self, event, callback):
        self.bindings[event] = callback

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
        cls.namespace = dict(PALETTE=PALETTE, apply_theme=lambda root: None,
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
                self.assertEqual(control.options.get("disabledforeground"), "#5C6270")
        self.assertEqual(self.viewer.text_entry.options.get("disabledbackground"), "#F1F3F8")

    def test_buttons_and_checkboxes_have_visible_keyboard_focus(self):
        controls = [self.viewer.control_toggle, *self.viewer.control_widgets]
        controls += [w for w in self.descendants() if w.options.get("text") in ("Звук", "Поверх")]
        for control in controls:
            with self.subTest(label=control.options.get("text", "entry")):
                self.assertTrue(control.options.get("takefocus"))
                self.assertGreaterEqual(control.options.get("highlightthickness", 0), 1)
                self.assertEqual(control.options.get("highlightcolor"), "#1A63E7")

    def test_checkmarks_are_dark_on_light_not_dark_on_dark(self):
        checks = [w for w in self.descendants() if "variable" in w.options]
        self.assertEqual(len(checks), 3)
        for check in checks:
            self.assertEqual(check.options["selectcolor"], "#FFFFFF")
            self.assertEqual(check.options["fg"], "#16181D")

    def test_viewport_stays_black_and_window_geometry_unchanged(self):
        self.assertEqual(self.viewer.root.window_geometry, "480x960+1380+60")
        self.assertEqual(self.viewer.image_label.options,
                         dict(bg="#000000", bd=0, highlightthickness=0,
                              padx=0, pady=0, anchor="center"))
        self.assertEqual(self.viewer.image_label.packing,
                         dict(side="top", fill="both", expand=True))
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


if __name__ == "__main__":
    unittest.main()
