"""Local A-share market-store owner: DuckDB source history, immutable captures.

This database contains **source observations**, not PIT-qualified signals or
orders. Qlib/Parquet are derived projections. TSP must not mutate this database.
DuckDB is single-writer; ingest and a separate read-only gateway must not run
against the same file concurrently.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from .tushare_source import SourceError, validate_symbol


SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS aql_schema_meta (
    schema_version INTEGER PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS captures (
    capture_id VARCHAR PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR NOT NULL CHECK (status IN ('RUNNING','COMPLETE','FAILED')),
    source_name VARCHAR NOT NULL,
    range_start DATE NOT NULL,
    range_end DATE NOT NULL,
    symbols_json VARCHAR NOT NULL,
    symbols_completed INTEGER NOT NULL DEFAULT 0,
    rows_captured BIGINT NOT NULL DEFAULT 0,
    failure_class VARCHAR
);
CREATE TABLE IF NOT EXISTS daily_bars (
    capture_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume_shares DOUBLE NOT NULL,
    amount_cny DOUBLE NOT NULL,
    cumulative_factor DOUBLE NOT NULL,
    source_captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (capture_id, symbol, trade_date)
);
CREATE TABLE IF NOT EXISTS trade_sessions (
    capture_id VARCHAR NOT NULL,
    cal_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    PRIMARY KEY (capture_id, cal_date)
);
"""


def require_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise SourceError("DuckDB missing; install the optional '.[storage]' dependency") from exc
    return duckdb


@contextmanager
def connect_store(path: Path, *, read_only: bool = False) -> Iterator[object]:
    duckdb = require_duckdb()
    db_file = path.expanduser().resolve()
    if read_only and not db_file.is_file():
        raise SourceError("market database not found; ingest source data before reading")
    if not read_only:
        db_file.parent.mkdir(parents=True, exist_ok=True)
    existed = db_file.is_file()
    try:
        conn = duckdb.connect(str(db_file), read_only=read_only)
    except duckdb.Error as exc:
        raise SourceError("market database unavailable or locked by another process") from exc
    try:
        if not existed and not read_only:
            conn.execute(SCHEMA)
            conn.execute(
                "INSERT INTO aql_schema_meta VALUES (?, now())",
                [SCHEMA_VERSION],
            )
        else:
            # NEVER attach or initialize a different DuckDB file, e.g. TSP's DB.
            try:
                row = conn.execute(
                    "SELECT schema_version FROM aql_schema_meta"
                ).fetchall()
            except duckdb.Error as exc:
                raise SourceError("existing database is not an AQL market store") from exc
            if len(row) != 1 or row[0][0] != SCHEMA_VERSION:
                raise SourceError("market database schema is missing or incompatible")
        yield conn
    finally:
        conn.close()


def latest_bars(conn, symbol: str, start: date, end: date) -> list[dict]:
    """Use only COMPLETE captures, latest revision per symbol/date."""
    validate_symbol(symbol)
    if start > end:
        raise ValueError("range start after end")
    sql = """
    WITH versions AS (
      SELECT b.symbol, b.trade_date, b.open, b.high, b.low, b.close,
             b.volume_shares, b.amount_cny, b.cumulative_factor,
             b.capture_id, c.completed_at,
             ROW_NUMBER() OVER (
               PARTITION BY b.symbol, b.trade_date
               ORDER BY c.completed_at DESC, b.capture_id DESC
             ) AS rn
      FROM daily_bars b
      JOIN captures c ON c.capture_id=b.capture_id
      WHERE c.status='COMPLETE' AND b.symbol=?
        AND b.trade_date >= ? AND b.trade_date <= ?
    )
    SELECT symbol, trade_date, open, high, low, close, volume_shares,
           amount_cny, cumulative_factor, capture_id, completed_at
    FROM versions WHERE rn=1 ORDER BY trade_date
    """
    result = conn.execute(sql, [symbol, start, end])
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def latest_capture_status(path: Path) -> dict:
    with connect_store(path, read_only=True) as conn:
        counts = conn.execute(
            "SELECT status, COUNT(*) AS n FROM captures GROUP BY status"
        ).fetchall()
        complete = conn.execute(
            """SELECT capture_id, range_start, range_end, symbols_completed,
                      rows_captured, completed_at
               FROM captures WHERE status='COMPLETE'
               ORDER BY completed_at DESC, capture_id DESC LIMIT 1"""
        ).fetchone()
    return {
        "database": str(path.expanduser().resolve()),
        "capture_counts": dict(counts),
        "latest_complete": None if complete is None else {
            "capture_id": complete[0],
            "range_start": str(complete[1]),
            "range_end": str(complete[2]),
            "symbols": complete[3],
            "rows": complete[4],
            "completed_at": complete[5].isoformat(),
        },
        "historical_PIT_qualified": False,
    }


def read_tsp_daily(conn, symbol: str, start: date, end: date) -> list[dict]:
    return [
        {
            "ts_code": row["symbol"],
            "trade_date": row["trade_date"].isoformat(),
            "open": row["open"], "high": row["high"], "low": row["low"],
            "close": row["close"], "vol": row["volume_shares"],
            "amt": row["amount_cny"],
        }
        for row in latest_bars(conn, symbol, start, end)
    ]


def read_tsp_factor_events(conn, symbol: str, start: date, end: date) -> list[dict]:
    """Cumulative snapshots -> per-event ratios. First available row is baseline.

    If source history starts after the stock was listed, an event on that first
    available day cannot be established, so this is not a dividend qualification.
    """
    bars = latest_bars(conn, symbol, date(1990, 1, 1), end)
    previous = None
    events = []
    for bar in bars:
        factor = bar["cumulative_factor"]
        if not math.isfinite(factor) or factor <= 0:
            raise SourceError("invalid cumulative adjustment factor in market store")
        if previous is not None and bar["trade_date"] >= start:
            ratio = factor / previous
            if not math.isclose(ratio, 1.0, rel_tol=1e-8, abs_tol=1e-9):
                events.append({
                    "ts_code": symbol,
                    "trade_date": bar["trade_date"].isoformat(),
                    "factor": ratio,
                })
        previous = factor
    return events
