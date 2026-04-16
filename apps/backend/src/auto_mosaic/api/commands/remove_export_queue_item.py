from __future__ import annotations

from auto_mosaic.api.commands._export_queue import remove_item as _remove_item


def run(payload: dict) -> dict:
    return _remove_item(payload)
