"""pytest configuration.

If ``ARCHIPELAGO_SRC`` env var points at an Archipelago source checkout
(and that checkout has its own venv with AP's runtime deps installed),
multidata tests can decode real seeds. Otherwise those tests skip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    ap_src = os.environ.get("ARCHIPELAGO_SRC")
    if ap_src and Path(ap_src).is_dir():
        sys.path.insert(0, ap_src)


@pytest.fixture
def ap_available() -> bool:
    try:
        import Utils  # noqa: F401
    except ImportError:
        return False
    return True
