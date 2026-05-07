"""
Ensure the repository root is importable.

The codebase (and tests) import modules via `from src...`. Under some pytest
import modes / tooling environments, the repo root may not be reliably present
on `sys.path` during collection. Python automatically imports `sitecustomize`
when present, so we can guarantee consistent imports without relying on shell
env vars.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

