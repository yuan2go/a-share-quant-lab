"""Publish a validated, read-only research snapshot to an explicit local TSP data path."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .artifacts import read_prediction_batch


def publish_to_tsp(study_dir: Path, tsp_data_dir: Path) -> dict:
    batch = read_prediction_batch(study_dir / "prediction-batch.json")
    report = json.loads((study_dir / "study-report.json").read_text(encoding="utf-8"))
    if report.get("run_id") != batch["run_id"]:
        raise ValueError("study report and predictions have inconsistent run_id")
    if report.get("status") != "RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED":
        raise ValueError("only explicit retrospective study reports are supported in v1")
    root = tsp_data_dir.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("TSP data directory missing")
    destination = root / "aql"
    destination.mkdir(exist_ok=True)
    contents = {
        "latest-prediction.json": json.dumps(batch, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8"),
        "latest-report.json": json.dumps(report, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8"),
    }
    # Files are read-only from TSP; avoid partially written JSON on process crash.
    for filename, data in contents.items():
        handle, name = tempfile.mkstemp(prefix=".aql-", suffix=".json", dir=destination)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, destination / filename)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {"status": "published_local_files", "run_id": batch["run_id"], "tsp_data_dir": str(root), "tsp_running_verified": False}
