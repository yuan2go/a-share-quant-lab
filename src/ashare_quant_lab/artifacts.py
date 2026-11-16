"""Read-only artifact consumption. Writing verified evidence is a later phase."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import validate_prediction_batch


def read_prediction_batch(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    return validate_prediction_batch(payload)
