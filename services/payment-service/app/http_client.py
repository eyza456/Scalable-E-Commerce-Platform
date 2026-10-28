"""Pool HTTP por proceso; cliente efimero para aislar headers y cookies por llamada."""
import threading
import httpx

_transport = None
_lock = threading.Lock()


def _new_transport():
    return httpx.HTTPTransport(trust_env=False, retries=0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))


def _pool():
    global _transport
    with _lock:
        if _transport is None:
            _transport = _new_transport()
        return _transport


class _BorrowedTransport(httpx.BaseTransport):
    def __init__(self, shared):
        self.shared = shared

    def handle_request(self, request):
        return self.shared.handle_request(request)

    def close(self):
        # El cliente de una llamada no es propietario del pool compartido.
        pass


def request(method, url, **kwargs):
    with httpx.Client(transport=_BorrowedTransport(_pool()), trust_env=False) as client:
        return client.request(method, url, **kwargs)


def get(url, **kwargs):
    return request("GET", url, **kwargs)


def post(url, **kwargs):
    return request("POST", url, **kwargs)


def close():
    global _transport
    with _lock:
        previous, _transport = _transport, None
    if previous is not None:
        previous.close()
