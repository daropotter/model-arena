"""Domain errors; the API turns them into HTTP statuses."""


class BillingError(Exception):
    status = 500

    def __init__(self, message=""):
        super().__init__(message)
        self.message = message or type(self).__name__


class BadRequest(BillingError):
    status = 400


class Unauthorized(BillingError):
    status = 401


class Forbidden(BillingError):
    status = 403


class NotFound(BillingError):
    status = 404


class Conflict(BillingError):
    status = 409


class GatewayError(Exception):
    """Base class for payment gateway failures."""


class GatewayDeclined(GatewayError):
    """The gateway refused the operation; nothing was charged or refunded."""


class GatewayTimeout(GatewayError):
    """No answer from the gateway. The operation may or may not have
    happened; its final state arrives later by webhook."""
