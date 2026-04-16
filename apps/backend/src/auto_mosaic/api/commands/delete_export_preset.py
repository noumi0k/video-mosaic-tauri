from __future__ import annotations

from auto_mosaic.api.commands._export_presets import delete_preset as _delete_preset


def run(payload: dict) -> dict:
    return _delete_preset(payload)
