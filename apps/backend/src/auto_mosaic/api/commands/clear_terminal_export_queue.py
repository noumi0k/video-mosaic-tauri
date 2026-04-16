from __future__ import annotations

from auto_mosaic.api.commands._export_queue import clear_terminal as _clear_terminal


def run(payload: dict) -> dict:
    return _clear_terminal(payload)
