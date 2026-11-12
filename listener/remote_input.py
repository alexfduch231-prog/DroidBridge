"""Bounded authenticated remote desktop input; coordinates match primary display capture."""
import ctypes
import hmac
import json
import math
import threading
import time
from urllib.parse import urlparse

_LOCK = threading.Lock()
_KEYS = {'win':0x5B,'esc':0x1B,'enter':0x0D,'tab':0x09,'backspace':0x08,
         'up':0x26,'down':0x28,'left':0x25,'right':0x27,'delete':0x2E}

def validate(event):
    if not isinstance(event, dict): raise ValueError('object required')
    action = event.get('action')
    if action not in ('click','drag','scroll','key','text','move_relative','focus'): raise ValueError('unknown action')
    if action == 'move_relative':
        for name in ('dx', 'dy'):
            value = event.get(name)
            if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError('invalid relative coordinate')
    if action in ('click','drag','scroll'):
        for key in (('x','y','x2','y2') if action == 'drag' else ('x','y')):
            v = event.get(key)
            if type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError('invalid coordinate')
    if action == 'click':
        if event.get('button','left') not in ('left','right'): raise ValueError('invalid button')
        if type(event.get('count',1)) is not int or event.get('count',1) not in (1,2): raise ValueError('invalid count')
    if action == 'drag':
        d=event.get('duration',400)
        if type(d) is not int or not 100 <= d <= 2000: raise ValueError('invalid duration')
    if action == 'scroll':
        d=event.get('delta')
        if type(d) is not int or not -10 <= d <= 10: raise ValueError('invalid scroll')
    if action == 'key' and event.get('name') not in _KEYS: raise ValueError('invalid key')
    if action == 'text':
        text=event.get('text')
        if not isinstance(text,str) or len(text)>2000 or '\x00' in text: raise ValueError('invalid text')
        text.encode('utf-16-le')
    return event


def dispatch(event, send, Input, Keyboard, Mouse, type_text):
    # Reuse the listener's existing and tested SendInput ABI.
    u = ctypes.windll.user32
    def move(x,y):
        width,height=u.GetSystemMetrics(0),u.GetSystemMetrics(1)
        if not u.SetCursorPos(round(x*(width-1)),round(y*(height-1))):
            raise OSError('cursor injection denied')
    def mouse(flags,data=0): send([Input(type=0,mi=Mouse(0,0,data & 0xffffffff,flags,0,0))])
    action=event['action']
    if action in ('click','drag'): move(event['x'],event['y'])
    if action == 'move_relative':
        from ctypes.wintypes import POINT
        point = POINT()
        if not u.GetCursorPos(ctypes.byref(point)):
            raise OSError('cursor position unavailable')
        width, height = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        x = max(0, min(width-1, point.x + round(event['dx'] * (width-1))))
        y = max(0, min(height-1, point.y + round(event['dy'] * (height-1))))
        if not u.SetCursorPos(x, y):
            raise OSError('cursor injection denied')
    elif action == 'click':
        down,up=(0x0002,0x0004) if event.get('button','left')=='left' else (0x0008,0x0010)
        for _ in range(event.get('count',1)):
            try: mouse(down)
            finally: mouse(up)
            time.sleep(.03)
    elif action == 'drag':
        try:
            mouse(0x0002)
            steps=max(5,event.get('duration',400)//16)
            for i in range(1,steps+1):
                f=i/steps
                move(event['x']+(event['x2']-event['x'])*f,event['y']+(event['y2']-event['y'])*f)
                time.sleep(event.get('duration',400)/1000/steps)
        finally: mouse(0x0004)
    elif action == 'scroll': mouse(0x0800,event['delta']*120)
    elif action == 'key':
        vk=_KEYS[event['name']]
        try: send([Input(type=1,ki=Keyboard(vk,0,0,0,0))])
        finally: send([Input(type=1,ki=Keyboard(vk,0,2,0,0))])
    elif action == 'text': type_text(event['text'])


def handle_input(handler):
    def reply(code,message):
        handler.send_bytes(code,'application/json; charset=utf-8',json.dumps(message).encode())
    if urlparse(handler.path).path != '/input':
        reply(404,{'ok':False,'error':'not_found'}); return
    want=handler.server.token
    got=handler.headers.get('Authorization','')
    if not want or not hmac.compare_digest(got.encode(),('Bearer '+want).encode()):
        reply(403,{'ok':False,'error':'unauthorized'}); return
    try:
        if handler.headers.get('Transfer-Encoding'): raise ValueError('encoding unsupported')
        lengths=handler.headers.get_all('Content-Length',[])
        if len(lengths)!=1 or not lengths[0].isdigit(): raise ValueError('length required')
        length=int(lengths[0])
        if length>8192:
            reply(413,{'ok':False,'error':'too_large'}); return
        handler.connection.settimeout(5)
        raw=handler.rfile.read(length)
        if len(raw)!=length: raise ValueError('truncated request')
        event=validate(json.loads(raw))
    except (ValueError,UnicodeError,OSError):
        reply(400,{'ok':False,'error':'invalid_input'}); return
    if event['action'] == 'focus':
        from focus_probe import editable_focus
        # No input lock or injection while waiting for an external UIA provider.
        if getattr(handler.server, 'dry_run', False):
            reply(200, {'ok': True, 'editable': None})
        else:
            reply(200, {'ok': True, 'editable': editable_focus()})
        return
    if not _LOCK.acquire(timeout=.1):
        reply(429,{'ok':False,'error':'busy'}); return
    try:
        if not getattr(handler.server, 'dry_run', False):
            handler.server.input_backend(event)
        reply(200,{'ok':True})
    except Exception:
        reply(500,{'ok':False,'error':'input_failed'})
    finally: _LOCK.release()
