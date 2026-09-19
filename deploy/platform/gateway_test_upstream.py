"""Synthetic test-only HTTP fixture; not a Torii API substitute."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

REQUEST_ID = "00000000-0000-4000-8000-000000000001"


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        body = json.dumps({"code": "fixture_denial", "request_id": REQUEST_ID}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/problem+json")
        self.send_header("X-Request-ID", REQUEST_ID)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        response = json.dumps({"bytes": len(body)}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Fixture).serve_forever()
