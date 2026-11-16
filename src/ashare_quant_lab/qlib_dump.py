"""Convert a verified frozen Parquet snapshot using Qlib's official dump_bin.py.

Qlib Binary remains Qlib's model-ready cache; the DuckDB capture store is the
local research source of truth. No CSV intermediary or homegrown bin writer.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
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
    cmd = [
        sys.executable, str(converter), "dump_all",
        "--data_path", str(base),
        "--qlib_dir", str(dest),
        "--freq", "day", "--max_workers", "4",
        "--file_suffix", ".parquet",
        "--include_fields", "open,high,low,close,vwap,volume,amount,factor",
    ]
    proc = subprocess.run(cmd, check=False)
    if proc.returncode:
        raise SourceError(f"official Qlib Parquet dump failed (exit={proc.returncode})")
    for name in ("calendars", "features", "instruments"):
        if not (dest / name).is_dir():
            raise SourceError(f"Qlib output incomplete: missing {name}")
    lineage = {
        "schema_version": 2,
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "converter_sha256": hashlib.sha256(converter.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "format": "parquet_to_qlib_binary",
    }
    (dest / "aql_source_manifest.json").write_text(
        json.dumps(lineage, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return {
        "provider_uri": str(dest), "status": "converted_by_official_qlib_dump",
        "source_snapshot_id": lineage["source_manifest_sha256"],
        "experiment_executed": False,
    }
