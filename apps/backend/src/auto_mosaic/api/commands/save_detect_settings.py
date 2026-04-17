from __future__ import annotations

from auto_mosaic.api.commands._detect_settings import save_settings as _save_settings


def run(payload: dict) -> dict:
    return _save_settings(payload)
