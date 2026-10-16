"""Transport-independent request/response types and a tiny router."""

import re
from dataclasses import dataclass, field

from .errors import BillingError


@dataclass
class Request:
    method: str
    path: str
    body: object = None
    headers: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)
    raw: bytes = b""


@dataclass
class Response:
    status: int
    body: object = None


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler):
        regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")
        self.routes.append((method, regex, handler))

    def dispatch(self, request):
        path_known = False
        for method, regex, handler in self.routes:
            match = regex.match(request.path)
            if not match:
                continue
            path_known = True
            if method != request.method:
                continue
            try:
                return handler(request, **match.groupdict())
            except BillingError as exc:
                return Response(exc.status, {"error": exc.message})
        if path_known:
            return Response(405, {"error": "method not allowed"})
        return Response(404, {"error": "not found"})
