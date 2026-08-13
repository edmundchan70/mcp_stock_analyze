"""Environment configuration for the scan server.

All secrets stay server-side (DATABASE_URL + the API keys the pipeline reads
from its own .env / environment). The frontend never sees these.
"""

from __future__ import annotations

import os

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/stock_analyze"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_output_root() -> str:
    return os.getenv("OUTPUT_ROOT", "output")
