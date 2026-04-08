from __future__ import annotations

import os
import site
import sys
from pathlib import Path


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[3] / "vendor"


def bootstrap_backend_environment() -> dict:
    vendor_root = _vendor_root()
    added_paths: list[str] = []

    if vendor_root.exists():
        site.addsitedir(str(vendor_root))
        normalized = str(vendor_root)
        sys.path = [path for path in sys.path if path != normalized]
        sys.path.insert(0, normalized)
        added_paths.append(str(vendor_root))

        if os.name == "nt":
            nvidia_root = vendor_root / "nvidia"
            if nvidia_root.exists():
                for bin_dir in nvidia_root.glob("*/bin"):
                    try:
                        os.add_dll_directory(str(bin_dir))
                        added_paths.append(str(bin_dir))
                    except (AttributeError, FileNotFoundError, OSError):
                        continue

    return {
        "vendor_root": str(vendor_root),
        "vendor_present": vendor_root.exists(),
        "added_paths": added_paths,
    }
