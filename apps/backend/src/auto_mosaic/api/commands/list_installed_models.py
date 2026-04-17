from __future__ import annotations

from auto_mosaic.api.commands._installed_models import list_installed as _list_installed


def run(payload: dict) -> dict:
    return _list_installed(payload)
