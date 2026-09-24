"""Service errors mapped to the response envelope (docs/03-link-service.md §3.2)."""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def invalid_request(message: str) -> ServiceError:
    return ServiceError(400, "invalid_request", message)


def unauthorized(message: str) -> ServiceError:
    return ServiceError(401, "unauthorized", message)


def not_found(message: str) -> ServiceError:
    return ServiceError(404, "not_found", message)


def upstream_error(message: str) -> ServiceError:
    return ServiceError(502, "upstream_error", message)
