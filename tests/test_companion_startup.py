"""Browser preconnect and startup evidence regressions; no hardware access."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from companion_http import CompanionHTTPServer, serialize_handlers
from companion_startup import StartupLog
from launch_companion import candidate_ports


class StartupTests(unittest.TestCase):
    def test_optional_test_port_is_bounded_and_default_unchanged(self):
        with patch.dict('os.environ', {}, clear=True):self.assertEqual(list(candidate_ports()),list(range(8787,8797)))
        with patch.dict('os.environ', {'FMER_PORT':'54321'}):self.assertEqual(candidate_ports(),(54321,))
        for value in ('0','65536','localhost','54321/path','-1'):
            with patch.dict('os.environ', {'FMER_PORT':value}),self.assertRaises(ValueError):candidate_ports()

    def server(self):
        state = {'active': 0, 'peak': 0, 'count': 0}
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup(); self.connection.settimeout(2)
            def log_message(self, *args): pass
            def send(self, status, payload):
                self.send_response(status); self.end_headers(); self.wfile.write(payload)
            def do_GET(self):
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
                previous = state['count']
                time.sleep(.02)
                state['count'] = previous + 1
                state['active'] -= 1
                self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
            do_POST = do_GET
        server = CompanionHTTPServer(('127.0.0.1', 0), serialize_handlers(Handler))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        return server, state

    def test_idle_browser_sockets_do_not_block_scripts(self):
        server, _ = self.server()
        sockets = [socket.create_connection(server.server_address) for _ in range(6)]
        for connection in sockets: self.addCleanup(connection.close)
        time.sleep(.05)
        with urlopen(f'http://127.0.0.1:{server.server_port}/companion_app.js', timeout=1) as response:
            self.assertEqual(response.read(), b'ok')

    def test_handlers_remain_serial_with_parallel_connections(self):
        server, state = self.server()
        def request(_):
            with urlopen(f'http://127.0.0.1:{server.server_port}/', timeout=3) as response:
                return response.read()
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(request, range(16))), [b'ok']*16)
        self.assertEqual(state, {'active': 0, 'peak': 1, 'count': 16})

    def test_closing_server_refuses_new_application_dispatch(self):
        server, state = self.server()
        with server.RequestHandlerClass.application_guard:
            server.application_closing = True
        with self.assertRaises(HTTPError) as caught:
            urlopen(f'http://127.0.0.1:{server.server_port}/', timeout=2)
        self.assertEqual(caught.exception.code, 503)
        self.assertEqual(state['count'], 0)

    def test_startup_log_bounded_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            log = StartupLog(folder)
            for i in range(100):
                log.record(dict(event='script_error', detail=str(i)+'x'*900, browser='Test browser'))
            self.assertLess(log.path.stat().st_size, 67000)
            self.assertTrue(log.path.with_suffix('.previous.jsonl').exists())
            result = StartupLog(folder).report('source')
            self.assertLessEqual(len(result['events']), 40)
            self.assertTrue(result['events'][-1]['detail'].startswith('99'))
            self.assertNotIn('patches', result)
            before = log.path.read_bytes()
            for bad in ({}, dict(event='x', detail='x'*1001, browser=''), dict(event='x', detail='', browser='', extra='bad')):
                with self.assertRaises(ValueError): log.record(bad)
            self.assertEqual(log.path.read_bytes(), before)


if __name__ == '__main__': unittest.main()
