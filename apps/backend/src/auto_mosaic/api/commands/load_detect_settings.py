from __future__ import annotations

from auto_mosaic.api.commands._detect_settings import load_settings as _load_settings


def run(payload: dict) -> dict:
    return _load_settings(payload)
