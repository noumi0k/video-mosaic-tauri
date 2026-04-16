from __future__ import annotations

from auto_mosaic.api.commands._export_queue import list_queue as _list_queue


def run(payload: dict) -> dict:
    return _list_queue(payload)
