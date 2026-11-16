"""DuckDB -> immutable per-security Parquet -> official Qlib dump_bin.py.

No CSV serialization in the active study. All bars selected from completed,
versioned captures. The Parquet files are derived from raw prices and the
source's cumulative adjustment factor; they are NOT a PIT proof.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from .market_store import connect_store
from .symbols import symbol_to_qlib
from .tushare_source import SourceError, validate_symbol


def _parquet_rows(bars: list[dict]) -> list[tuple]:
    if not bars:
        raise SourceError("cannot export an empty historical symbol")
    first_factor = bars[0]["cumulative_factor"]
    if not math.isfinite(first_factor) or first_factor <= 0:
        raise SourceError("invalid reference cumulative adjustment factor")
    output = []
    for row in bars:
        factor = row["cumulative_factor"]
        volume, amount = row["volume_shares"], row["amount_cny"]
        if not math.isfinite(factor) or factor <= 0 or volume <= 0 or amount <= 0:
            raise SourceError("incomplete factor/volume/amount for Qlib Parquet conversion")
        ratio = factor / first_factor
        output.append((
            row["trade_date"],
            row["open"] * ratio, row["high"] * ratio,
            row["low"] * ratio, row["close"] * ratio,
            amount / volume * ratio, volume / ratio,
            amount, ratio,
        ))
    return output


def export_market_parquet(
    database: Path,
    symbols: list[str],
    start: date,
    end: date,
    output_dir: Path,
    *,
    min_history: int = 60,
    capture_id: str | None = None,
) -> dict:
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("nonempty unique symbol list required")
    symbols = sorted(validate_symbol(symbol) for symbol in symbols)
    if start > end or min_history <= 0:
        raise ValueError("invalid export date range or min_history")
    destination = output_dir.expanduser().resolve()
    if destination.exists():
        raise FileExistsError("immutable Parquet snapshot already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aql-parquet-", dir=destination.parent))
    try:
        with connect_store(database, read_only=True) as conn:
            # Never stitch cumulative factors from independently revised histories.
            candidates = conn.execute(
                """SELECT capture_id, symbols_json FROM captures
                   WHERE status='COMPLETE' AND range_start<=? AND range_end>=?
                   ORDER BY completed_at DESC, capture_id DESC""", [start, end]).fetchall()
            eligible = [cid for cid, cohort in candidates if set(symbols) <= set(json.loads(cohort))]
            if capture_id is None:
                capture_id = eligible[0] if eligible else None
            if capture_id not in eligible:
                raise SourceError("no single complete capture covers the requested range/cohort")
            calendar = conn.execute(
                """SELECT cal_date FROM trade_sessions WHERE capture_id=? AND is_open
                   AND cal_date>=? AND cal_date<=? ORDER BY cal_date""",
                [capture_id, start, end]).fetchall()
            sessions = len(calendar)
            if sessions < min_history:
                raise SourceError("exchange calendar too short for this study")
            summary = []
            capture_ids: set[str] = set()
            for symbol in symbols:
                result = conn.execute(
                    """SELECT * FROM daily_bars WHERE capture_id=? AND symbol=?
                       AND trade_date>=? AND trade_date<=? ORDER BY trade_date""",
                    [capture_id, symbol, start, end])
                columns = [col[0] for col in result.description]
                bars = [dict(zip(columns, row)) for row in result.fetchall()]
                if len(bars) < min_history:
                    raise SourceError(f"insufficient recorded bars for {symbol}: {len(bars)}")
                prepared = _parquet_rows(bars)
                # Temporary memory table avoids pandas/CSV and copies only this symbol.
                conn.execute(
                    """CREATE TEMPORARY TABLE aql_export (
                         date DATE, open DOUBLE, high DOUBLE, low DOUBLE,
                         close DOUBLE, vwap DOUBLE, volume DOUBLE,
                         amount DOUBLE, factor DOUBLE
                    )"""
                )
                try:
                    conn.executemany(
                        "INSERT INTO aql_export VALUES (?,?,?,?,?,?,?,?,?)",
                        prepared,
                    )
                    filename = symbol_to_qlib(symbol) + ".parquet"
                    path = stage / filename
                    safe_path = str(path).replace("'", "''")
                    conn.execute(
                        f"COPY aql_export TO '{safe_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
                    )
                finally:
                    conn.execute("DROP TABLE aql_export")
                capture_ids.update(str(b["capture_id"]) for b in bars)
                summary.append({
                    "symbol": symbol, "file": filename, "rows": len(bars),
                    "first": bars[0]["trade_date"].isoformat(),
                    "last": bars[-1]["trade_date"].isoformat(),
                    "open_sessions_in_requested_range": sessions,
                    "coverage_ratio_not_suspension_adjusted": round(len(bars) / sessions, 5),
                    "missing_open_dates_unclassified": sorted({d[0].isoformat() for d in calendar}
                                                             - {b["trade_date"].isoformat() for b in bars}),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                })
        manifest = {
            "schema_version": 2,
            "file_format": "parquet",
            "source": "Tushare-compatible HTTP proxy in DuckDB",
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "point_in_time_status": "RETROSPECTIVE_ONLY",
            "survivorship_status": "FIXED_COHORT_NOT_PIT_VALIDATED",
            "source_endpoint": "DuckDB complete captures: daily + adj_factor + trade_cal",
            "database_role": "source_of_truth_local_market_store",
            "source_capture_ids": sorted(capture_ids),
            "capture_selection": "single_complete_capture_no_revision_stitching",
            "open_dates": [d[0].isoformat() for d in calendar],
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
            "price": "raw_price * cumulative_adj_factor / first_valid_factor",
            "volume": "shares / relative_factor",
            "amount": "CNY",
            "universe": symbols,
            "files": summary,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        (stage / "manifest.json").write_bytes(manifest_bytes)
        os.replace(stage, destination)
        return {
            "status": "RETROSPECTIVE_ONLY",
            "snapshot_dir": str(destination),
            "data_snapshot_id": hashlib.sha256(manifest_bytes).hexdigest(),
            "symbols": len(symbols),
            "rows": sum(row["rows"] for row in summary),
            "source_captures": len(capture_ids),
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
