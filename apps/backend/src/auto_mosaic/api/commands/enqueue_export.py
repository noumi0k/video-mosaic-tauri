from __future__ import annotations

from auto_mosaic.api.commands._export_queue import enqueue as _enqueue


def run(payload: dict) -> dict:
    return _enqueue(payload)
