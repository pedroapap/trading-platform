"""Domain errors raised by services; app.main maps them to HTTP responses.

Messages are written for API clients and returned as the response `detail`.
"""


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    """The resource does not exist, or belongs to someone else (404)."""


class ConflictError(DomainError):
    """The request is not allowed in the resource's current state (409)."""


class InvalidOperationError(DomainError):
    """The request contradicts the resource's own data, e.g. an exit before the entry (422)."""
