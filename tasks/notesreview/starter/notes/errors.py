"""HTTP errors raised by handlers and turned into responses by the router."""


class HTTPError(Exception):
    status = 500
    message = "internal error"

    def __init__(self, message=None):
        super().__init__(message or self.message)
        self.message = message or self.message


class BadRequest(HTTPError):
    status = 400
    message = "bad request"


class Unauthorized(HTTPError):
    status = 401
    message = "authentication required"


class Forbidden(HTTPError):
    status = 403
    message = "forbidden"


class NotFound(HTTPError):
    status = 404
    message = "not found"


class Conflict(HTTPError):
    status = 409
    message = "conflict"
