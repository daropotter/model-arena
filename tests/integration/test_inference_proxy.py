"""Integration tests for runner/ollama_proxy.py.

Runs entirely locally: a fake upstream HTTP server records every request
and an `ollama_proxy.py` subprocess is started in front of it. No real
LLM, internet, or docker is required.
"""

import http.client
import json
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.support import RUNNER, free_port

HEALTH_PATH = "/__arena_health"
HEALTH_BODY = b"model-arena-inference-proxy\n"
MODELS_BODY = json.dumps({
    "object": "list",
    "data": [{"id": "fake:latest", "object": "model"}],
}, separators=(",", ":")).encode("utf-8")
COMPLETIONS_BODY = json.dumps({
    "id": "cmpl-fake",
    "object": "text_completion",
    "choices": [],
}, separators=(",", ":")).encode("utf-8")
CHAT_REQUEST = json.dumps({
    "model": "fake:latest",
    "messages": [{"role": "user", "content": "ping"}],
    "stream": False,
}, separators=(",", ":")).encode("utf-8")

STREAM_PAUSE_S = 0.8
# Deliberately small (like a real Ollama NDJSON token): the proxy must
# forward bytes as soon as they are available, not wait for a 64 KiB read to
# fill. This is the regression guard for incremental streaming.
FIRST_CHUNK = b'{"chunk":"one"}'
SECOND_CHUNK = b'{"chunk":"two"}'
STREAM_BODY = FIRST_CHUNK + SECOND_CHUNK


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    """Records every request; serves deterministic canned responses."""

    protocol_version = "HTTP/1.1"
    server_version = "FakeOllama"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _request_body(self):
        raw = self.headers.get("Content-Length", "0")
        try:
            length = int(raw)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _record(self, body):
        entry = {
            "method": self.command,
            "path": self.path,
            "body": body,
            "headers": {key: value for key, value in self.headers.items()},
        }
        with self.server.requests_lock:
            self.server.requests.append(entry)

    def _reply(self, body, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
            self.wfile.flush()

    def _reply_stream(self):
        body = self.server.stream_body
        split = self.server.stream_split
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body[:split])
        self.wfile.flush()
        time.sleep(self.server.stream_pause)
        self.wfile.write(body[split:])
        self.wfile.flush()

    def _handle(self):
        self._record(self._request_body())
        path = self.path.split("?", 1)[0]
        if self.command == "GET" and path == "/v1/models":
            self._reply(MODELS_BODY)
        elif self.command == "POST" and path == "/v1/chat/completions":
            self._reply_stream()
        elif self.command == "POST" and path == "/v1/completions":
            self._reply(COMPLETIONS_BODY)
        else:
            self._reply(b'{"ok":true}')

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle


class FakeUpstream(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address):
        super().__init__(address, FakeUpstreamHandler)
        self.requests = []
        self.requests_lock = threading.Lock()
        self.stream_body = STREAM_BODY
        self.stream_split = len(FIRST_CHUNK)
        self.stream_pause = STREAM_PAUSE_S

    def seen(self, method=None, path=None):
        with self.requests_lock:
            return [
                entry for entry in self.requests
                if (method is None or entry["method"] == method)
                and (path is None or entry["path"] == path)
            ]


class InferenceProxyTest(unittest.TestCase):

    def setUp(self):
        self.upstream_port = free_port()
        self.proxy_port = free_port()
        while self.proxy_port == self.upstream_port:
            self.proxy_port = free_port()

        self.upstream = FakeUpstream(("127.0.0.1", self.upstream_port))
        threading.Thread(
            target=self.upstream.serve_forever, daemon=True).start()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)

        self.proxy = subprocess.Popen(
            [sys.executable, str(RUNNER / "ollama_proxy.py"),
             "--listen", "127.0.0.1",
             "--listen-port", str(self.proxy_port),
             "--target", "127.0.0.1",
             "--target-port", str(self.upstream_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._stop_proxy)
        self._wait_for_health()

    def _stop_proxy(self):
        proc = self.proxy
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if proc.stderr is not None:
            proc.stderr.close()

    def _wait_for_health(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if self.proxy.poll() is not None:
                break
            try:
                status, body = self._proxy_request("GET", HEALTH_PATH)
            except (OSError, http.client.HTTPException) as exc:
                last_error = repr(exc)
            else:
                if status == 200 and body == HEALTH_BODY:
                    return
                last_error = f"status={status} body={body!r}"
            time.sleep(0.05)

        stderr = ""
        if self.proxy.poll() is not None and self.proxy.stderr is not None:
            try:
                stderr = self.proxy.stderr.read()
            except (OSError, ValueError):
                stderr = ""
        self.fail(
            f"proxy on 127.0.0.1:{self.proxy_port} never became healthy "
            f"within {timeout:.0f}s (exit={self.proxy.poll()}, "
            f"last_error={last_error}, stderr={stderr[-2000:]!r})")

    def _proxy_request(self, method, path, body=None, headers=None,
                       timeout=10):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = response.read()
            return response.status, data
        finally:
            conn.close()

    def _raw_status_line(self, request, timeout=5):
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=timeout)
        try:
            sock.sendall(request)
            data = b""
            while b"\r\n" not in data:
                piece = sock.recv(1024)
                if not piece:
                    break
                data += piece
            return data.split(b"\r\n", 1)[0]
        finally:
            sock.close()

    def test_health_endpoint_body(self):
        status, body = self._proxy_request("GET", HEALTH_PATH)
        self.assertEqual(status, 200)
        self.assertEqual(body, HEALTH_BODY)
        self.assertEqual(self.upstream.seen(), [])

    def test_get_models_is_forwarded(self):
        status, body = self._proxy_request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(body, MODELS_BODY)
        records = self.upstream.seen("GET", "/v1/models")
        self.assertEqual(len(records), 1)

    def test_chat_completions_body_forwarded_byte_identical(self):
        status, _ = self._proxy_request(
            "POST", "/v1/chat/completions", body=CHAT_REQUEST,
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        records = self.upstream.seen("POST", "/v1/chat/completions")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["body"], CHAT_REQUEST)

    def test_forbidden_post_not_forwarded(self):
        status, _ = self._proxy_request(
            "POST", "/api/delete", body=b'{"name":"x"}',
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(self.upstream.seen(path="/api/delete"), [])

    def test_forbidden_get_not_forwarded(self):
        status, _ = self._proxy_request("GET", "/api/pull")
        self.assertEqual(status, 403)
        self.assertEqual(self.upstream.seen(path="/api/pull"), [])

    def test_unsupported_method_not_forwarded(self):
        status, _ = self._proxy_request("PUT", "/v1/models")
        self.assertIn(status, (403, 501))
        self.assertEqual(self.upstream.seen(path="/v1/models"), [])

    def test_oversized_content_length_rejected_from_headers(self):
        status_line = self._raw_status_line(
            b"POST /v1/chat/completions HTTP/1.0\r\n"
            b"Host: x\r\n"
            b"Content-Length: 999999999\r\n"
            b"\r\n"
            b"xxxx")
        self.assertIn(b"413", status_line)
        self.assertEqual(self.upstream.seen(), [])

    def test_invalid_content_length_rejected(self):
        status_line = self._raw_status_line(
            b"POST /v1/chat/completions HTTP/1.0\r\n"
            b"Host: x\r\n"
            b"Content-Length: abc\r\n"
            b"\r\n")
        self.assertIn(b"400", status_line)
        self.assertEqual(self.upstream.seen(), [])

    def test_streaming_first_bytes_arrive_before_upstream_finishes(self):
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=5)
        try:
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.0\r\n"
                b"Host: x\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(CHAT_REQUEST)).encode() +
                b"\r\n\r\n" + CHAT_REQUEST)

            start = time.monotonic()
            header = b""
            while b"\r\n\r\n" not in header:
                piece = sock.recv(1)
                if not piece:
                    self.fail("connection closed before response headers")
                header += piece
            status_line, _, raw_headers = header.partition(b"\r\n")
            self.assertIn(b" 200 ", status_line)

            content_length = None
            for line in raw_headers.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    content_length = int(line.split(b":", 1)[1].strip())
            self.assertIsNotNone(content_length)
            self.assertEqual(content_length, len(STREAM_BODY))

            body = b""
            first_body_at = None
            while len(body) < content_length:
                piece = sock.recv(min(4096, content_length - len(body)))
                if not piece:
                    self.fail("connection closed before body completed")
                if first_body_at is None:
                    first_body_at = time.monotonic()
                body += piece
            finished = time.monotonic()
        finally:
            sock.close()

        self.assertIsNotNone(first_body_at)
        self.assertLess(first_body_at - start, 0.7)
        self.assertGreater(finished - start, 0.8)
        self.assertIn(FIRST_CHUNK, body)
        self.assertIn(SECOND_CHUNK, body)
        self.assertEqual(body, STREAM_BODY)


if __name__ == "__main__":
    unittest.main()
