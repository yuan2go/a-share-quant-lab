"""Reproducible retrospective CSV preparation for Qlib's official dump_bin.py.

This uses current Tushare cumulative adjustment-factor history, so it is
RETROSPECTIVE, not evidence of historical point-in-time availability.
Never write credentials or account data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .tushare_source import SourceError, TushareClient, daily_rows, factor_snapshots, validate_symbol

CSV_FIELDS = ("date", "open", "high", "low", "close", "vwap", "volume", "amount", "factor")


def symbol_to_qlib(symbol: str) -> str:
    validate_symbol(symbol)
    code, market = symbol.split(".")
    return f"{market}{code}"


def qlib_to_symbol(instrument: str) -> str:
    if not isinstance(instrument, str) or len(instrument) != 8:
        raise ValueError("invalid Qlib instrument")
    market, code = instrument[:2].upper(), instrument[2:]
    symbol = f"{code}.{market}"
    validate_symbol(symbol)
    return symbol


def load_symbols(path: Path) -> list[str]:
    values = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    symbols = [validate_symbol(v) for v in values if v]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("symbol file must contain unique, nonempty A-share symbols")
    return sorted(symbols)


def build_adjusted_csv_rows(bars: list[dict], factors: dict[str, float]) -> list[dict]:
    """Normalize adjusted OHLC/VWAP, inverse-scale share volume, retain raw amount."""
    if not bars:
        raise SourceError("no daily rows")
    if not all(bar["trade_date"] in factors for bar in bars):
        raise SourceError("factor coverage does not match all daily trading dates")
    first = factors[bars[0]["trade_date"]]
    if first <= 0:
        raise SourceError("invalid reference adjustment factor")
    result = []
    for bar in bars:
        ratio = factors[bar["trade_date"]] / first
        volume = bar["vol"]
        if volume <= 0 or bar["amt"] <= 0:
            raise SourceError("cannot synthesize VWAP for missing/zero volume or amount")
        vwap = bar["amt"] / volume * ratio
        result.append({
            "date": bar["trade_date"],
            **{k: bar[k] * ratio for k in ("open", "high", "low", "close")},
            "vwap": vwap, "volume": volume / ratio,
            "amount": bar["amt"], "factor": ratio,
        })
    return result


def export_qlib_csv(
    source: TushareClient,
    symbols: list[str],
    start: date,
    end: date,
    output_dir: Path,
    *,
    pace_seconds: float = 0,
) -> dict:
    if start > end or (end - start).days > 5500:
        raise ValueError("invalid requested range; split >5500 calendar-day requests")
    if pace_seconds < 0:
        raise ValueError("pace_seconds cannot be negative")
    symbols = sorted({validate_symbol(sym) for sym in symbols})
    if not symbols:
        raise ValueError("no symbols")
    destination = output_dir.resolve()
    if destination.exists():
        raise FileExistsError("snapshot directory already exists; immutable snapshots cannot be overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aql-stage-", dir=destination.parent))
    rows_summary = []
    try:
        for symbol in symbols:
            bars = daily_rows(source, symbol, start, end)
            if pace_seconds:
                time.sleep(pace_seconds)
            factors = factor_snapshots(source, symbol, start, end)
            if pace_seconds:
                time.sleep(pace_seconds)
            records = build_adjusted_csv_rows(bars, factors)
            filename = symbol_to_qlib(symbol) + ".csv"
            target = stage / filename
            with target.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerows(records)
            content_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            rows_summary.append({
                "symbol": symbol,
                "file": filename,
                "rows": len(records),
                "first": records[0]["date"],
                "last": records[-1]["date"],
                "sha256": content_hash,
            })
        captured_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": 1,
            "source": "Tushare-compatible HTTP proxy",
            "capture_timestamp": captured_at,
            "point_in_time_status": "RETROSPECTIVE_ONLY",
            "survivorship_status": "FIXED_COHORT_NOT_PIT_VALIDATED",
            "source_endpoint": "daily + adj_factor",
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
            "price": "raw_price * cumulative_adj_factor / first_valid_factor",
            "volume": "shares / relative_factor",
            "amount": "CNY",
            "universe": symbols,
            "files": rows_summary,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        (stage / "manifest.json").write_bytes(manifest_bytes)
        os.replace(stage, destination)
        return {"snapshot_dir": str(destination), "data_snapshot_id": hashlib.sha256(manifest_bytes).hexdigest(), "symbols": len(symbols), "rows": sum(s["rows"] for s in rows_summary), "status": "RETROSPECTIVE_ONLY"}
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
