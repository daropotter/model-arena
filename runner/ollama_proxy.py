#!/usr/bin/env python3
"""Restricted HTTP proxy from arena-net to Ollama's inference API."""

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ALLOWED = {
    ("GET", "/v1/models"),
    ("POST", "/v1/chat/completions"),
    ("POST", "/v1/completions"),
}
MAX_BODY = 16 * 1024 * 1024
REQUEST_HOP = {"connection", "keep-alive", "proxy-authenticate",
               "proxy-authorization", "te", "trailers", "transfer-encoding",
               "upgrade", "content-length"}
RESPONSE_HOP = {"connection", "keep-alive", "proxy-authenticate",
                "proxy-authorization", "te", "trailers", "transfer-encoding",
                "upgrade"}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    target_host = "127.0.0.1"
    target_port = 11434

    def do_GET(self):
        if self.path == "/__arena_health":
            body = b"model-arena-inference-proxy\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._forward()

    def do_POST(self):
        self._forward()

    def _forward(self):
        path = self.path.split("?", 1)[0]
        if (self.command, path) not in ALLOWED:
            self.send_error(403, "only Ollama inference endpoints are allowed")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if length < 0 or length > MAX_BODY:
            self.send_error(413, "request too large")
            return
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in REQUEST_HOP and key.lower() != "host"}
        connection = http.client.HTTPConnection(
            self.target_host, self.target_port, timeout=10)
        try:
            connection.connect()
            connection.sock.settimeout(None)
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in RESPONSE_HOP:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException) as exc:
            if not self.wfile.closed:
                self.send_error(502, str(exc))
        finally:
            connection.close()

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} {fmt % args}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=11435)
    parser.add_argument("--target", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=11434)
    args = parser.parse_args()
    ProxyHandler.target_host = args.target
    ProxyHandler.target_port = args.target_port
    server = ThreadingHTTPServer((args.listen, args.listen_port), ProxyHandler)
    print(f"proxy {args.listen}:{args.listen_port} -> "
          f"{args.target}:{args.target_port} (inference only)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
