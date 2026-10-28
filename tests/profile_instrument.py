"""Instrumentacion diagnostica, inyectada SOLO en la copia Docker de perfilado."""
from contextvars import ContextVar
from functools import wraps
import inspect
import json
import re
import time
import uuid

CURRENT = ContextVar("request_profile", default=None)


def timed_call(label, call, *args, **kwargs):
    state = CURRENT.get()
    start = time.perf_counter()
    try:
        return call(*args, **kwargs)
    finally:
        if state is not None:
            state[label] += (time.perf_counter() - start) * 1000


def install(app, engine, service):
    try:
        import httpx
    except ImportError:
        httpx = None
    if httpx is not None:
        original_init, original_send = httpx.Client.__init__, httpx.Client.send

        @wraps(original_init)
        def init(self, *args, **kwargs):
            return timed_call("http_client_init_ms", original_init, self, *args, **kwargs)

        @wraps(original_send)
        def send(self, request, *args, **kwargs):
            state = CURRENT.get()
            if state is not None:
                request.headers.setdefault("X-Profile-Trace", state["trace"])
                state["http_calls"] += 1
            return timed_call("http_send_ms", original_send, self, request, *args, **kwargs)

        httpx.Client.__init__, httpx.Client.send = init, send
    import urllib.request
    original_urlopen = urllib.request.urlopen

    @wraps(original_urlopen)
    def urlopen(request, *args, **kwargs):
        state = CURRENT.get()
        if state is not None:
            state["http_calls"] += 1
            if isinstance(request, urllib.request.Request):
                request.add_unredirected_header("X-Profile-Trace", state["trace"])
        return timed_call("http_send_ms", original_urlopen, request, *args, **kwargs)

    urllib.request.urlopen = urlopen
    if engine is not None:
        from sqlalchemy import event
        connect = engine.connect

        def measured_connect(*args, **kwargs):
            return timed_call("db_connect_ms", connect, *args, **kwargs)

        engine.connect = measured_connect

        @event.listens_for(engine, "before_cursor_execute")
        def before(conn, cursor, statement, parameters, context, executemany):
            context.profile_data = (CURRENT.get(), time.perf_counter())

        @event.listens_for(engine, "after_cursor_execute")
        def after(conn, cursor, statement, parameters, context, executemany):
            state, start = context.profile_data
            if state is not None:
                elapsed = (time.perf_counter() - start) * 1000
                state["db_execute_ms"] += elapsed
                table = re.search(r"\b(?:FROM|INTO|UPDATE)\s+([\w.]+)", statement, re.I)
                state["sql"].append({"table": table.group(1) if table else "lock_or_other", "ms": elapsed})

        @event.listens_for(engine.pool, "checkout")
        def checkout(connection, record, proxy):
            record.info["profile_lease"] = (CURRENT.get(), time.perf_counter())

        @event.listens_for(engine.pool, "checkin")
        def checkin(connection, record):
            state, start = record.info.pop("profile_lease", (None, 0))
            if state is not None:
                state["db_held_ms"] += (time.perf_counter() - start) * 1000
    if engine is not None:
        from sqlalchemy.orm import Query
        original_all = Query.all

        @wraps(original_all)
        def query_all(self, *args, **kwargs):
            return timed_call("orm_all_ms", original_all, self, *args, **kwargs)

        Query.all = query_all
    import fastapi.routing
    original_serialize = fastapi.routing.serialize_response
    if inspect.iscoroutinefunction(original_serialize):
        @wraps(original_serialize)
        async def serialize(*args, **kwargs):
            state, start = CURRENT.get(), time.perf_counter()
            try:
                return await original_serialize(*args, **kwargs)
            finally:
                if state is not None:
                    state["serialize_ms"] += (time.perf_counter() - start) * 1000
        fastapi.routing.serialize_response = serialize

    class ProfileMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or scope["path"] == "/health":
                return await self.app(scope, receive, send)
            headers = dict(scope["headers"])
            state = {"service": service, "method": scope["method"], "path": re.sub(r"/\d+(?=/|$)", "/{id}", scope["path"]),
                     "trace": headers.get(b"x-profile-trace", uuid.uuid4().hex.encode()).decode(), "status": 0,
                     **{k: 0 for k in ("http_client_init_ms", "http_send_ms", "http_calls", "db_connect_ms", "db_execute_ms", "db_held_ms", "orm_all_ms", "serialize_ms")}, "sql": []}
            token, start = CURRENT.set(state), time.perf_counter()

            async def measured_send(message):
                if message["type"] == "http.response.start":
                    state["status"] = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, measured_send)
            finally:
                state["total_ms"] = (time.perf_counter() - start) * 1000
                print("PERF_PROFILE " + json.dumps(state), flush=True)
                CURRENT.reset(token)

    app.add_middleware(ProfileMiddleware)
