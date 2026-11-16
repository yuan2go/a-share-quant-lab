"""Tushare -> DuckDB capture transaction, with incremental immutable versions."""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from .market_store import connect_store
from .tushare_source import (
    SourceError, TushareClient, daily_rows, factor_snapshots, parse_day, validate_symbol
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sessions(source: TushareClient, start: date, end: date) -> list[tuple[date, bool]]:
    rows = source.query(
        "trade_cal", exchange="SSE",
        start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"),
    )
    calendar = {}
    for row in rows:
        day = parse_day(row["cal_date"])
        if not start <= day <= end or day in calendar:
            raise SourceError("invalid/duplicate source trade-calendar date")
        status = str(row["is_open"])
        if status not in ("0", "1"):
            raise SourceError("invalid exchange trade-calendar status")
        calendar[day] = status == "1"
    if not calendar or min(calendar) > start or max(calendar) < end:
        raise SourceError("trade-calendar range incomplete")
    if not any(calendar.values()):
        raise SourceError("no open sessions in source date range")
    return sorted(calendar.items())


def ingest_market(
    database: Path,
    source: TushareClient,
    symbols: list[str],
    start: date,
    end: date,
    *,
    pace_seconds: float = 0.0,
) -> dict:
    if start > end or pace_seconds < 0 or (end - start).days > 5500:
        raise ValueError("invalid ingestion range or pacing")
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("nonempty unique symbol list required")
    symbols = sorted(validate_symbol(s) for s in symbols)
    capture_id = uuid.uuid4().hex
    with connect_store(database) as conn:
        conn.execute(
            """INSERT INTO captures
               (capture_id, started_at, status, source_name, range_start, range_end, symbols_json)
               VALUES (?, ?, 'RUNNING', 'tushare-http', ?, ?, ?)""",
            [capture_id, _utcnow(), start, end, json.dumps(symbols)],
        )
        try:
            sessions = _sessions(source, start, end)
            open_dates = {d for d, is_open in sessions if is_open}
            total = 0
            for symbol in symbols:
                bars = daily_rows(source, symbol, start, end)
                if pace_seconds:
                    time.sleep(pace_seconds)
                factors = factor_snapshots(source, symbol, start, end)
                if pace_seconds:
                    time.sleep(pace_seconds)
                if not bars or any(row["trade_date"] not in factors for row in bars):
                    raise SourceError("daily/adjustment source coverage missing for requested security")
                captured = _utcnow()
                prepared = []
                for row in bars:
                    day = date.fromisoformat(row["trade_date"])
                    if day not in open_dates:
                        raise SourceError("daily market bar conflicts with source trade calendar")
                    prepared.append((
                        capture_id, symbol, day,
                        row["open"], row["high"], row["low"], row["close"],
                        row["vol"], row["amt"], factors[row["trade_date"]], captured,
                    ))
                conn.execute("BEGIN TRANSACTION")
                try:
                    conn.executemany(
                        """INSERT INTO daily_bars
                           (capture_id, symbol, trade_date, open, high, low, close,
                            volume_shares, amount_cny, cumulative_factor, source_captured_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        prepared,
                    )
                    conn.execute("UPDATE captures SET symbols_completed=symbols_completed+1, rows_captured=rows_captured+? WHERE capture_id=?", [len(prepared), capture_id])
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                total += len(prepared)

            conn.execute("BEGIN TRANSACTION")
            try:
                conn.executemany(
                    "INSERT INTO trade_sessions (capture_id, cal_date, is_open) VALUES (?,?,?)",
                    [(capture_id, d, status) for d, status in sessions],
                )
                conn.execute(
                    "UPDATE captures SET status='COMPLETE', completed_at=? WHERE capture_id=?",
                    [_utcnow(), capture_id],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            return {
                "capture_id": capture_id, "status": "SOURCE_RECEIVED_NOT_PIT_QUALIFIED",
                "symbols": len(symbols), "daily_rows": total,
                "sessions": len(sessions), "database": str(database.resolve()),
            }
        except BaseException as exc:
            # Failed captures cannot participate in any query/export. Remove their
            # incomplete content; retain their status and reason class for audit.
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute("DELETE FROM daily_bars WHERE capture_id=?", [capture_id])
                conn.execute("DELETE FROM trade_sessions WHERE capture_id=?", [capture_id])
                conn.execute(
                    """UPDATE captures SET status='FAILED', completed_at=?,
                           failure_class=?, symbols_completed=0, rows_captured=0
                       WHERE capture_id=?""",
                    [_utcnow(), type(exc).__name__, capture_id],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            raise
