"""Bounded socket concurrency with serialized application dispatch.

Browsers may open speculative connections without sending a request. A plain
HTTPServer waits on those sockets before serving scripts on other connections.
Only parsing is concurrent here: the existing library/render/device handlers
still run one at a time. This does not parallelize device operations.
"""
from functools import wraps
from http.server import ThreadingHTTPServer
import threading


class CompanionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self._connections = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


def serialize_handlers(handler):
    guard = threading.RLock()
    def serialized(method):
        @wraps(method)
        def dispatch(self):
            with guard:
                if getattr(self.server, 'application_closing', False):
                    self.send(503, b'{"error":"Companion is closing. Reopen the application."}')
                    return
                return method(self)
        return dispatch
    for name in ('do_GET', 'do_POST'):
        setattr(handler, name, serialized(getattr(handler, name)))
    handler.application_guard = guard
    return handler
