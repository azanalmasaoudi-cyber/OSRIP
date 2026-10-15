"""Stable, user-explainable API errors (booklet 3.12).

Services raise ``ApiError`` with a machine code and a plain message; the app
handler renders ``{"error": {"code", "message", "details"?}}``. Database
internals, SQL and credentials are never included.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


def not_found(entity: str) -> ApiError:
    return ApiError(404, "not_found", f"The {entity} does not exist or is not visible to you.")


def conflict(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(409, code, message, details)


def unprocessable(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(422, code, message, details)
