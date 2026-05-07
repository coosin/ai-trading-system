from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root_on_syspath() -> None:
    # tests/* live at <repo>/tests/..., so repo root is parents[1]
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_repo_root_on_syspath()

