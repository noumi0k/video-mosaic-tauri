from __future__ import annotations


def success(command: str, data: dict | list | None = None, warnings: list[str] | None = None) -> dict:
    return {
        "ok": True,
        "command": command,
        "data": data if data is not None else {},
        "error": None,
        "warnings": warnings or [],
    }


def failure(
    command: str,
    code: str,
    message: str,
    details: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "ok": False,
        "command": command,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "warnings": warnings or [],
    }
