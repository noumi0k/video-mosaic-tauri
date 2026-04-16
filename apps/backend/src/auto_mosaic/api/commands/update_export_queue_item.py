from __future__ import annotations

from auto_mosaic.api.commands._export_queue import update_item as _update_item


def run(payload: dict) -> dict:
    return _update_item(payload)
