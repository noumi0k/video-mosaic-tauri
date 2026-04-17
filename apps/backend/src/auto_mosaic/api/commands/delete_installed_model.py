from __future__ import annotations

from auto_mosaic.api.commands._installed_models import delete_installed as _delete_installed


def run(payload: dict) -> dict:
    return _delete_installed(payload)
