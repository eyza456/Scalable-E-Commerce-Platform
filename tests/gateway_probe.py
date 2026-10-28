"""Backend de eco exclusivo de la prueba aislada del gateway."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Probe(BaseHTTPRequestHandler):
    def respond(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        query = parse_qs(urlsplit(self.path).query)
        self.send_response(int(query.get("status", [200])[0]))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "probe": os.getenv("PROBE_ID"), "method": self.command, "path": self.path,
            "body": json.loads(body) if body else None, "headers": dict(self.headers),
        }).encode())

    do_GET = do_POST = do_PUT = do_DELETE = respond

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8000), Probe).serve_forever()
