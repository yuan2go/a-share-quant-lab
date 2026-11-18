"""TSP backend extension. No model, trading or third-party HTTP calls in web workers."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from app.extensions import BACKEND_EXTENSION_API_VERSION

EXTENSION_ID = "aql.research"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION
_root: Path | None = None


def setup(registrar):
    router = APIRouter(prefix="/api/extensions/aql.research", tags=["AQL research"])

    @router.get("/latest")
    def latest() -> dict[str, Any]:
        if _root is None:
            raise HTTPException(status_code=503, detail="research extension not initialized")
        prediction_file = _root / "aql" / "latest-prediction.json"
        report_file = _root / "aql" / "latest-report.json"
        if not prediction_file.is_file() or not report_file.is_file():
            return {"status": "NO_RESEARCH_DATA", "predictions": [], "note": "Run and publish a local Qlib study first."}
        if prediction_file.stat().st_size > 5_000_000 or report_file.stat().st_size > 1_000_000:
            raise HTTPException(status_code=422, detail="research output exceeds size limit")
        try:
            batch = json.loads(prediction_file.read_text(encoding="utf-8"))
            report = json.loads(report_file.read_text(encoding="utf-8"))
            if (batch.get("schema_version") != 1 or batch.get("market") != "CN-A" or
                batch.get("run_id") != report.get("run_id") or
                report.get("status") != "RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED" or
                not isinstance(batch.get("predictions"), list)):
                raise ValueError("inconsistent research artifacts")
            return {
                "status": "RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED",
                "run_id": batch["run_id"],
                "created_at": batch["created_at"],
                "signal_cutoff": batch["signal_cutoff"],
                "forecast_horizon_days": batch["forecast_horizon_days"],
                "model_id": batch["model_id"],
                "rank_ic_difference": report.get("paired_ic_difference"),
                "predictions": batch["predictions"][:250],
                "note": "Fixed-cohort, historical ranking only. Not a current buy/sell signal or verified after-cost strategy.",
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="invalid research artifacts") from None

    @router.get("/direction")
    def direction() -> dict[str, Any]:
        if _root is None:
            raise HTTPException(status_code=503, detail="extension not initialized")
        path = _root / "aql" / "latest-direction.json"
        if not path.is_file():
            return {"kind": "NO_DIRECTION_DATA"}
        try:
            if path.stat().st_size > 5_000_000:
                raise ValueError("oversized direction snapshot")
            summary = json.loads(path.read_text())
            if summary["kind"] != "DIRECTION_FORWARD_SUMMARY":
                raise ValueError("invalid summary")
            return {**{key: summary[key] for key in ("kind", "latest", "paired", "historical")},
                    "archive": summary.get("archive", [])}
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(status_code=422, detail="invalid direction snapshot") from None

    @router.get("/direction/{key}")
    def archived_direction(key: str) -> dict[str, Any]:
        if _root is None or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise HTTPException(status_code=404)
        path = _root / "aql" / "direction-reviews" / (key + ".json")
        if not path.is_file():
            raise HTTPException(status_code=404)
        if path.stat().st_size > 1_000_000:
            raise HTTPException(status_code=422, detail="oversized batch")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise HTTPException(status_code=422, detail="invalid archived batch")
        return json.loads(raw)

    registrar.include_router(router)


def startup(context):
    global _root
    _root = Path(context.data_dir).resolve()
