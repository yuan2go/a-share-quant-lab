"""Minimal schema validation for immutable, read-only model prediction artifacts.

A valid artifact only proves its shape. It does NOT prove point-in-time
availability, model efficacy, historical execution, or economic alpha.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1
_A_SHARE_SYMBOL = re.compile(r"[0-9]{6}\.(?:SH|SZ)\Z")
_REQUIRED_BATCH = frozenset(
    {
        "schema_version",
        "run_id",
        "created_at",
        "signal_cutoff",
        "market",
        "forecast_horizon_days",
        "model_id",
        "universe_id",
        "data_snapshot_id",
        "predictions",
    }
)


class ArtifactValidationError(ValueError):
    """Invalid result format; not an assessment of prediction quality."""


def _aware_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{field} must be an ISO-8601 datetime string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactValidationError(f"{field} has invalid datetime format") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ArtifactValidationError(f"{field} must include a timezone offset")
    return dt


def validate_prediction_batch(payload: object) -> dict[str, Any]:
    """Validate a V1 prediction batch without modifying its content."""
    if not isinstance(payload, dict):
        raise ArtifactValidationError("prediction batch must be a JSON object")

    missing = _REQUIRED_BATCH - payload.keys()
    unexpected = payload.keys() - _REQUIRED_BATCH
    if missing or unexpected:
        raise ArtifactValidationError(
            f"batch keys mismatch; missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )

    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise ArtifactValidationError("unsupported schema_version; expected integer 1")
    if payload["market"] != "CN-A":
        raise ArtifactValidationError("market must be CN-A")

    for name in ("run_id", "model_id", "universe_id", "data_snapshot_id"):
        value = payload[name]
        if not isinstance(value, str) or not value.strip():
            raise ArtifactValidationError(f"{name} must be non-empty text")

    horizon = payload["forecast_horizon_days"]
    if type(horizon) is not int or horizon < 1:
        raise ArtifactValidationError("forecast_horizon_days must be a positive integer")

    created = _aware_datetime(payload["created_at"], "created_at")
    cutoff = _aware_datetime(payload["signal_cutoff"], "signal_cutoff")
    if created < cutoff:
        raise ArtifactValidationError("created_at cannot precede signal_cutoff")

    predictions = payload["predictions"]
    if not isinstance(predictions, list):
        raise ArtifactValidationError("predictions must be an array (empty is allowed)")
    symbols: set[str] = set()
    for i, row in enumerate(predictions):
        if not isinstance(row, dict) or set(row) != {"symbol", "score"}:
            raise ArtifactValidationError(f"predictions[{i}] must contain symbol and score only")
        symbol = row["symbol"]
        if not isinstance(symbol, str) or not _A_SHARE_SYMBOL.fullmatch(symbol):
            raise ArtifactValidationError(f"predictions[{i}].symbol must be NNNNNN.SH/SZ")
        if symbol in symbols:
            raise ArtifactValidationError(f"duplicate prediction symbol: {symbol}")
        symbols.add(symbol)
        score = row["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ArtifactValidationError(f"predictions[{i}].score must be a finite number")

    return payload
