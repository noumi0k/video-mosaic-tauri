from __future__ import annotations

from auto_mosaic.api.commands._export_presets import save_preset as _save_preset


def run(payload: dict) -> dict:
    return _save_preset(payload)
