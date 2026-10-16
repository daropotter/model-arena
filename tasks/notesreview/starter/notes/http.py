"""Transport-independent request/response types and a tiny router."""

import re
from dataclasses import dataclass, field

from .errors import HTTPError


@dataclass
class Request:
    method: str
    path: str
    body: object = None
    headers: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: object = None
    content_type: str = "application/json"


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler):
        regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")
        self.routes.append((method, regex, handler))

    def dispatch(self, request):
        allowed = False
        for method, regex, handler in self.routes:
            match = regex.match(request.path)
            if not match:
                continue
            allowed = True
            if method != request.method:
                continue
            try:
                return handler(request, **match.groupdict())
            except HTTPError as exc:
                return Response(exc.status, {"error": exc.message})
        if allowed:
            return Response(405, {"error": "method not allowed"})
        return Response(404, {"error": "not found"})
