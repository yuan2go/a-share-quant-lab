"""Convert a verified frozen Parquet snapshot using Qlib's official dump_bin.py.

Qlib Binary remains Qlib's model-ready cache; the DuckDB capture store is the
local research source of truth. No CSV intermediary or homegrown bin writer.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import os
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .tushare_source import SourceError


def dump_parquet_using_official_qlib(qlib_repo: Path, snapshot_dir: Path, provider_uri: Path) -> dict:
    converter = qlib_repo.expanduser().resolve() / "scripts" / "dump_bin.py"
    base = snapshot_dir.expanduser().resolve()
    manifest_path = base / "manifest.json"
    if not converter.is_file() or not manifest_path.is_file():
        raise SourceError("Qlib converter or Parquet snapshot manifest missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 2 or manifest.get("file_format") != "parquet"
            or manifest.get("point_in_time_status") != "RETROSPECTIVE_ONLY"
            or not isinstance(manifest.get("files"), list)
            or not manifest["files"]):
        raise SourceError("invalid or unsupported Parquet snapshot manifest")
    names = set()
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise SourceError("invalid source snapshot file entry")
        filename = item.get("file")
        if (not isinstance(filename, str) or not filename.endswith(".parquet")
                or filename != Path(filename).name or filename in names):
            raise SourceError("unsafe, duplicate or missing Parquet filename")
        names.add(filename)
        file_path = base / filename
        if not file_path.is_file() or hashlib.sha256(file_path.read_bytes()).hexdigest() != item.get("sha256"):
            raise SourceError("Parquet bytes differ from immutable source manifest")
    actual = {p.name for p in base.glob("*.parquet")}
    if actual != names:
        raise SourceError("Parquet snapshot contains files not declared in manifest")

    dest = provider_uri.expanduser().resolve()
    if dest.exists():
        raise FileExistsError("Qlib output directory exists: never silently overwrite research data")
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aql-binary-", dir=dest.parent))
    cmd = [
        sys.executable, str(converter), "dump_all",
        "--data_path", str(base),
        "--qlib_dir", str(stage),
        "--freq", "day", "--max_workers", "4",
        "--file_suffix", ".parquet",
        "--include_fields", "open,high,low,close,vwap,volume,amount,factor",
    ]
    try:
        proc = subprocess.run(cmd, check=False)
        if proc.returncode:
            raise SourceError(f"official Qlib Parquet dump failed (exit={proc.returncode})")
        for name in ("calendars", "features", "instruments"):
            if not (stage / name).is_dir():
                raise SourceError(f"Qlib output incomplete: missing {name}")
        audit = verify_projection(base, stage, manifest)
        converter_revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=converter.parent.parent,
                                            capture_output=True, text=True, check=False)
        lineage = {
            "schema_version": 3,
            "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "qlib_version": importlib.metadata.version("pyqlib"),
            "converter_git_revision": converter_revision.stdout.strip(),
            "converter_sha256": hashlib.sha256(converter.read_bytes()).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "format": "parquet_to_qlib_binary", "projection_audit": audit,
            "binary_files": binary_hashes(stage),
        }
        (stage / "aql_source_manifest.json").write_text(
            json.dumps(lineage, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(stage, dest)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {"provider_uri": str(dest), "status": "converted_and_values_verified",
            "source_snapshot_id": lineage["source_manifest_sha256"],
            "projection_audit": audit, "experiment_executed": False}


def binary_hashes(provider):
    return {str(p.relative_to(provider)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ("calendars", "features", "instruments")
            for p in sorted((provider / directory).rglob("*")) if p.is_file()}


def verify_binary_identity(provider):
    lineage = json.loads((provider / "aql_source_manifest.json").read_text())
    if not lineage.get("binary_files") or binary_hashes(provider) != lineage["binary_files"]:
        raise SourceError("Qlib Binary bytes differ from verified projection; convert a fresh provider")


def verify_projection(snapshot, provider, manifest):
    """Read official float32 binaries independently and check every source value.

    This audits serialization only; native D.features is separately exercised by
    the study. No custom Binary writer or alternate model engine is involved.
    """
    import numpy as np
    import pandas as pd

    calendar = pd.DatetimeIndex(pd.read_csv(provider / "calendars/day.txt", header=None)[0])
    expected_calendar = pd.DatetimeIndex(manifest.get("open_dates", []))
    if not len(expected_calendar) or not calendar.equals(expected_calendar):
        raise SourceError("Qlib calendar differs from captured exchange open dates")
    fields = ("open", "high", "low", "close", "vwap", "volume", "amount", "factor")
    count = 0
    for item in manifest["files"]:
        frame = pd.read_parquet(snapshot / item["file"]).set_index("date").sort_index()
        frame.index = pd.DatetimeIndex(frame.index)
        instrument = Path(item["file"]).stem.lower()
        for field in fields:
            data = np.fromfile(provider / "features" / instrument / f"{field}.day.bin", dtype="<f4")
            if not len(data) or not np.isfinite(data[0]) or int(data[0]) != data[0]:
                raise SourceError("invalid official Binary start index")
            start = int(data[0])
            if start < 0 or start + len(data) - 1 > len(calendar):
                raise SourceError("official Binary outside exchange calendar")
            actual = pd.Series(data[1:], index=calendar[start:start + len(data) - 1])
            wanted = frame[field].reindex(actual.index)
            if (not frame.index.isin(actual.index).all()
                    or not np.allclose(actual.values, wanted.values, rtol=2e-6, atol=1e-7, equal_nan=True)):
                raise SourceError(f"official Binary value mismatch: {instrument}/{field}")
            count += len(frame)
    return {"status": "ALL_PARQUET_VALUES_MATCH_FLOAT32_BINARY", "checked_field_values": count,
            "calendar_sessions": len(calendar), "rtol": 2e-6, "atol": 1e-7}
