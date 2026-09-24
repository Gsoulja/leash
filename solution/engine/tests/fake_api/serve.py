"""The fake platform as a local service, for Compose and the connection check (LEASH-127). Never the live API.

    PYTHONPATH=tests uv run uvicorn --factory fake_api.serve:create_app --port 9000

It serves the real challenge pack, so it reports the pack's data version and a 0.x API version: the worker's
compatibility check (config.check_compatibility) then accepts it exactly as it would the platform.
"""

import os
from pathlib import Path
from typing import Any

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack

DATA = Path(__file__).resolve().parents[4] / "data"


def create_app() -> Any:
    fake = FakeViseca(Pack(Path(os.environ.get("LEASH_DATA_DIR", str(DATA)))),
                      api_key=os.environ.get("FAKE_API_KEY", "fake-team-key"),
                      human_window_seconds=float(os.environ.get("FAKE_HUMAN_WINDOW_SECONDS", "120")),
                      api_version="0.fake", data_version=os.environ.get("FAKE_DATA_VERSION", "saw26"))
    return fake.app
