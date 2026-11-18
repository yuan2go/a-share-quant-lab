"""Publish a validated, read-only research snapshot to an explicit local TSP data path."""

from __future__ import annotations

import hashlib
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
        "latest-prediction.json": json.dumps(
            batch, ensure_ascii=False, allow_nan=False, sort_keys=True
        ).encode("utf-8"),
        "latest-report.json": json.dumps(
            report, ensure_ascii=False, allow_nan=False, sort_keys=True
        ).encode("utf-8"),
    }
    # Files are read-only from TSP; avoid partially written JSON on process crash.
    for filename, data in contents.items():
        _replace_file(destination / filename, data)
    return {
        "status": "published_local_files",
        "run_id": batch["run_id"],
        "tsp_data_dir": str(root),
        "tsp_running_verified": False,
    }


def publish_direction(summary_path, tsp_data_dir):
    root = Path(tsp_data_dir).resolve(strict=True) / "aql"
    root.mkdir(exist_ok=True)
    summary = json.loads(summary_path.read_text())
    if summary.get("kind") != "DIRECTION_FORWARD_SUMMARY":
        raise ValueError("expected forward summary")
    reports = Path(__file__).resolve().parents[2] / "docs/research"
    comparison = json.loads((reports / "direction-refit-comparison.json").read_text())
    old = json.loads((reports / "direction-forecast-20261117-summary.json").read_text())
    package = summary["latest"]["work_package"]
    if package not in (comparison["candidate_work_package"], old["work_package"]):
        raise ValueError("unknown direction experiment")
    summary["historical"] = dict(
        original=old["model_adoption"],
        candidate=comparison["conclusion"],
        candidate_adoption="RESEARCH_ONLY_DO_NOT_ADOPT",
        original_loss=comparison["common"]["original"]["log_loss"],
        candidate_loss=comparison["common"]["model"]["log_loss"],
    )
    archive = root / "direction-reviews"
    archive.mkdir(exist_ok=True)
    index = []
    for view in summary.pop("views", [summary["latest"]]):
        payload = json.dumps(view, sort_keys=True, allow_nan=False).encode()
        key = hashlib.sha256(payload).hexdigest()
        destination = archive / (key + ".json")
        if not destination.exists():
            _replace_file(destination, payload)
        index.append(
            dict(
                key=key,
                generated_at=view["generated_at"],
                date=view["data_through"],
                prediction_sha256=view["prediction_sha256"],
                maturity=view["maturity"],
            )
        )
    summary["archive"] = index
    summary.pop("batches")  # full audit retained in research output
    _replace_file(root / "latest-direction.json", json.dumps(summary, allow_nan=False).encode())
    return {"status": "PUBLISHED_DIRECTION", "prediction_sha256": summary["latest"]["prediction_sha256"]}


def _replace_file(destination, payload):
    handle, temporary = tempfile.mkstemp(prefix=".aql-", dir=destination.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
