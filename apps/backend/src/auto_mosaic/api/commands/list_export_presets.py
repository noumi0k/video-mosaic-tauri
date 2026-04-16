from __future__ import annotations

from auto_mosaic.api.commands._export_presets import list_presets as _list_presets


def run(payload: dict) -> dict:
    return _list_presets(payload)
