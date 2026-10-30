"""Run in a fresh Python process per service: importing ASGI must be inert."""

from contextlib import ExitStack
import importlib.util
import socket
import threading
from unittest.mock import patch


def forbidden(*args, **kwargs):
    raise AssertionError("Import attempted database/network access or started a worker")


with ExitStack() as guards:
    guards.enter_context(patch.object(threading.Thread, "start", side_effect=forbidden))
    guards.enter_context(patch.object(socket.socket, "connect", side_effect=forbidden))
    if importlib.util.find_spec("sqlalchemy"):
        from sqlalchemy.engine import Engine

        guards.enter_context(patch.object(Engine, "connect", side_effect=forbidden))
    if importlib.util.find_spec("pika"):
        guards.enter_context(patch("pika.BlockingConnection", side_effect=forbidden))
    from app.main import app

    assert any(getattr(route, "path", None) == "/health" for route in app.routes)

print("OK: ASGI import without SQL, sockets or background threads")
