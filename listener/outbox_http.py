"""Bounded authenticated reads of files explicitly staged on this PC."""
import hashlib
import hmac
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from file_outbox import Outbox, OutboxError


def handle_outbox(handler):
    def reply(code, payload):
        handler.close_connection = True
        handler.send_bytes(code, 'application/json; charset=utf-8',
                           json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    expected = ('Bearer ' + handler.server.token).encode('utf-8')
    actual = handler.headers.get('Authorization', '').encode('utf-8')
    if not handler.server.token or not hmac.compare_digest(actual, expected):
        reply(403, {'ok': False, 'error': 'Unauthorized'})
        return
    try:
        lengths = handler.headers.get_all('Content-Length', [])
        if (handler.headers.get('Transfer-Encoding') or len(lengths) != 1
                or not lengths[0].isascii() or not lengths[0].isdigit()
                or not 0 < int(lengths[0]) <= 4096):
            raise OutboxError('Invalid request length')
        handler.connection.settimeout(15)
        raw = handler.rfile.read(int(lengths[0]))
        if len(raw) != int(lengths[0]):
            raise OutboxError('Incomplete request')
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise OutboxError('Invalid request')
        store = Outbox(getattr(handler.server, 'upload_data_dir',
                              os.environ.get('VZAIMOPULT_DATA_DIR') or Path(__file__).parent))
        route = urlparse(handler.path).path
        if route == '/outbox/list' and not request:
            reply(200, {'ok': True, 'files': store.pending()})
        elif route == '/outbox/chunk' and set(request) == {'id', 'offset'}:
            block = store.chunk(request['id'], request['offset'])
            handler.close_connection = True
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/octet-stream')
            handler.send_header('Content-Length', str(len(block)))
            handler.send_header('X-Chunk-SHA256', hashlib.sha256(block).hexdigest())
            handler.send_header('Connection', 'close')
            handler.end_headers()
            handler.wfile.write(block)
        elif route == '/outbox/ack' and set(request) == {'id', 'sha256'}:
            store.ack(request['id'], request['sha256'])
            reply(200, {'ok': True})
        else:
            raise OutboxError('Unknown operation')
    except (OutboxError, ValueError, TypeError, RecursionError, OSError):
        reply(400, {'ok': False, 'error': 'Transfer unavailable or invalid request'})
