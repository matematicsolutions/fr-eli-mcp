"""Pytest fixtures + .env loader for the live smoke tests.

The connector reads PISTE credentials from the environment only. For local smoke runs we
load ``.env`` (gitignored) into ``os.environ`` here so the live tests can authenticate.
Offline tests (drift, parse) do not need credentials.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not clobber a value already set in the real environment.
        os.environ.setdefault(key, value)


_load_dotenv()
