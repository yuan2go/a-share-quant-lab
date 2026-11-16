"""Call Qlib's official CSV->bin converter, not a second in-house storage engine."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .tushare_source import SourceError


def dump_csv_using_official_qlib(qlib_repo: Path, csv_dir: Path, provider_uri: Path) -> dict:
    converter = qlib_repo.resolve() / "scripts" / "dump_bin.py"
    manifest = csv_dir.resolve() / "manifest.json"
    if not converter.is_file() or not manifest.is_file():
        raise SourceError("Qlib source checkout/dump_bin.py or CSV manifest is missing")
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    if source_manifest.get("schema_version") != 1 or not isinstance(source_manifest.get("files"), list):
        raise SourceError("invalid CSV snapshot manifest")
    for entry in source_manifest["files"]:
        name = entry.get("file", "")
        if not isinstance(name, str) or not name.endswith(".csv") or "/" in name or "\\" in name:
            raise SourceError("invalid CSV filename in snapshot manifest")
        raw_path = csv_dir.resolve() / name
        if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise SourceError("CSV file differs from immutable source manifest")
    dest = provider_uri.resolve()
    if dest.exists():
        raise FileExistsError("Qlib output directory already exists; create a new snapshot path")
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(converter), "dump_all",
        "--data_path", str(csv_dir.resolve()),
        "--qlib_dir", str(dest),
        "--freq", "day",
        "--max_workers", "4",
        "--include_fields", "open,high,low,close,vwap,volume,amount,factor",
    ]
    # Official converter requires pandas, numpy and fire in this environment.
    # It writes no stock-selection or trade recommendations.
    proc = subprocess.run(command, check=False)
    if proc.returncode != 0:
        raise SourceError(f"official Qlib dump failed (exit={proc.returncode}); inspect local logs")
    for required in ("calendars", "features", "instruments"):
        if not (dest / required).is_dir():
            raise SourceError(f"Qlib output incomplete: missing {required}")
    lineage = {
        "schema_version": 1,
        "source_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "converter_sha256": hashlib.sha256(converter.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest / "aql_source_manifest.json").write_text(
        json.dumps(lineage, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return {"provider_uri": str(dest), "status": "converted_by_official_dump", "experiment_executed": False}
