import http.client
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('input_listener', Path(__file__).with_name('pc-listener.py'))
listener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(listener)

class InputTests(unittest.TestCase):
    def setUp(self):
        self.server = listener.Server(('127.0.0.1', 0), listener.Handler)
        self.server.token = 'test-secret'
        self.server.input_backend = Mock()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, event, token='test-secret', raw=None, extra=None):
        body = json.dumps(event).encode() if raw is None else raw
        c = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        headers.update(extra or {})
        c.request('POST', '/input', body, headers)
        r = c.getresponse()
        result = r.status, r.read()
        c.close()
        return result[0]

    def test_authorized_click_dispatched(self):
        event = {'action':'click', 'x':0.25, 'y':0.75, 'button':'left', 'count':1}
        self.assertEqual(200, self.post(event))
        self.server.input_backend.assert_called_once_with(event)

    def test_dry_run_does_not_inject(self):
        self.server.dry_run = True
        self.assertEqual(200,self.post(dict(action='key',name='win')))
        self.server.input_backend.assert_not_called()

    def test_denied_never_dispatches(self):
        self.assertEqual(403, self.post({'action':'key','name':'win'}, token='wrong'))
        self.server.input_backend.assert_not_called()

    def test_relative_move_authorized_and_bounded(self):
        event = dict(action='move_relative', dx=.125, dy=-.25)
        self.assertEqual(200, self.post(event))
        self.server.input_backend.assert_called_once_with(event)
        self.server.input_backend.reset_mock()
        for value in [True, float('nan'), float('inf'), -1.01, 1.01, '1', None]:
            with self.subTest(value=value):
                self.assertEqual(400, self.post(dict(action='move_relative', dx=value, dy=0)))
        self.server.input_backend.assert_not_called()

    def test_focus_probe_is_authenticated_and_does_not_inject(self):
        import focus_probe
        with patch.object(focus_probe, 'editable_focus', return_value=True) as probe:
            self.assertEqual(403, self.post(dict(action='focus'), token='wrong'))
            probe.assert_not_called()
            self.assertEqual(200, self.post(dict(action='focus')))
            probe.assert_called_once()
        self.server.input_backend.assert_not_called()

    def test_all_actions(self):
        for event in [dict(action='drag',x=0,y=0,x2=1,y2=1,duration=100),
                      dict(action='scroll',x=.5,y=.5,delta=-3),
                      dict(action='key',name='win'),dict(action='text',text='Привет 👋')]:
            with self.subTest(event=event): self.assertEqual(200,self.post(event))
        self.assertEqual(4,self.server.input_backend.call_count)

    def test_bad_events_rejected_without_input(self):
        for event in [[], None, {}, dict(action='exec',text='cmd'), dict(action='key',name='power'),
                      dict(action='click',x=-1,y=.5), dict(action='click',x=True,y=.5),
                      dict(action='click',x=float('nan'),y=.5), dict(action='click',x=1.01,y=.5),
                      dict(action='click',x=.5,y=.5,button='bad'),dict(action='click',x=.5,y=.5,count=9),
                      dict(action='drag',x=0,y=0,x2=1,y2=1,duration=9000),
                      dict(action='text',text='x'*2001),dict(action='scroll',x=0,y=0,delta=100)]:
            with self.subTest(event=event): self.assertEqual(400,self.post(event))
        self.server.input_backend.assert_not_called()

    def test_malformed_or_oversize_rejected(self):
        self.assertEqual(400,self.post({},raw=b'{invalid'))
        self.assertEqual(413,self.post({},raw=b' '*8193))
        self.assertEqual(400,self.post({},extra={'Transfer-Encoding':'chunked'}))
        self.server.input_backend.assert_not_called()

class DispatchTests(unittest.TestCase):
    def test_trackpad_scroll_preserves_cursor(self):
        import remote_input
        user=Mock()
        with patch.object(remote_input.ctypes.windll,'user32',user):
            remote_input.dispatch(dict(action='scroll',x=.5,y=.5,delta=1),Mock(),
                listener.INPUT,listener.KEYBDINPUT,listener.MOUSEINPUT,Mock())
        user.SetCursorPos.assert_not_called()

    def test_delete_key_is_supported(self):
        import remote_input
        self.assertEqual('delete',remote_input.validate(dict(action='key',name='delete'))['name'])

    def test_relative_move_clamps_without_mouse_buttons(self):
        import remote_input
        def cursor(pointer):
            pointer._obj.x, pointer._obj.y = 1800, 20
            return 1
        user = Mock()
        user.GetCursorPos.side_effect = cursor
        user.GetSystemMetrics.side_effect = lambda axis: 1920 if axis == 0 else 1080
        user.SetCursorPos.return_value = 1
        send = Mock()
        with patch.object(remote_input.ctypes.windll, 'user32', user):
            remote_input.dispatch(dict(action='move_relative', dx=.5, dy=-.5), send,
                listener.INPUT, listener.KEYBDINPUT, listener.MOUSEINPUT, Mock())
        user.SetCursorPos.assert_called_once_with(1919, 0)
        send.assert_not_called()

    def test_drag_always_releases_mouse(self):
        import remote_input
        send=Mock()
        user=Mock()
        user.GetSystemMetrics.return_value=1920
        user.SetCursorPos.side_effect=[1, 0]
        with patch.object(remote_input.ctypes.windll, 'user32', user):
            with self.assertRaises(OSError):
                remote_input.dispatch(dict(action='drag',x=0,y=0,x2=1,y2=1,duration=100),
                    send,listener.INPUT,listener.KEYBDINPUT,listener.MOUSEINPUT,Mock())
        self.assertEqual([2,4], [call.args[0][0].mi.dwFlags for call in send.call_args_list])

    def test_key_release_on_injection_failure(self):
        import remote_input
        send=Mock(side_effect=[OSError('denied'),None])
        with self.assertRaises(OSError):
            remote_input.dispatch(dict(action='key',name='win'),send,
                listener.INPUT,listener.KEYBDINPUT,listener.MOUSEINPUT,Mock())
        self.assertEqual([0,2], [call.args[0][0].ki.dwFlags for call in send.call_args_list])

if __name__ == '__main__': unittest.main()
