"""The assistant is a separate package from the engine; it imports `leash` read-only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
