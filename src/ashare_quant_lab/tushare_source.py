"""Credential-safe Tushare-compatible HTTP client and A-share normalization.

Responses are untrusted external data. Never log request bodies or credentials.
Daily bars: Tushare vol=100 shares, amount=1000 CNY.
TSP ex_factor: single-event ratio, unlike Tushare cumulative adj_factor.
"""
from __future__ import annotations

import json
import gzip
import io
import math
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

_SYMBOL = re.compile(r"^[0-9]{6}\.(?:SH|SZ)$")
_API = frozenset({"trade_cal", "daily", "adj_factor", "stock_basic"})
FIELDS = {
    "daily": "ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
    "adj_factor": "ts_code,trade_date,adj_factor",
    "trade_cal": "exchange,cal_date,is_open,pretrade_date",
    "stock_basic": "ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status",
}


class SourceError(RuntimeError):
    """A source failure. Messages never include credentials or raw HTTP body."""


def parse_day(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be ISO or YYYYMMDD")
    try:
        return date.fromisoformat(value[:10]) if "-" in value else datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise ValueError("expected A-share symbol NNNNNN.SH or NNNNNN.SZ")
    return symbol


def valid_number(value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise SourceError("invalid numeric field")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise SourceError("invalid numeric field") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise SourceError("invalid numeric field")
    return number


class TushareClient:
    """Compatible with the user's POST proxy; no Tushare SDK/private API needed."""

    def __init__(self, token: str | None = None, url: str | None = None, timeout: float = 25):
        self._token = token if token is not None else os.getenv("TUSHARE_TOKEN", "")
        self.url = url or os.getenv("TUSHARE_HTTP_URL", "https://t.xiaodefa.top/")
        self.timeout = timeout
        if not self._token:
            raise SourceError("TUSHARE_TOKEN is missing; set a local environment variable")
        if not self.url.startswith("https://"):
            raise SourceError("TUSHARE_HTTP_URL must be HTTPS")

    def query(self, api_name: str, **params: str) -> list[dict[str, Any]]:
        if api_name not in _API:
            raise SourceError("unsupported Tushare API name")
        request_body = {
            "api_name": api_name,
            "token": self._token,
            "params": params,
            "fields": FIELDS[api_name],
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(request_body, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise SourceError(f"Tushare HTTP status {response.status}")
                body = response.read(12_000_001)
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(12_000_001)
        except (urllib.error.URLError, TimeoutError, OSError, EOFError) as exc:
            raise SourceError(f"Tushare transport error ({type(exc).__name__})") from None
        if len(body) > 12_000_000:
            raise SourceError("Tushare response too large")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceError("invalid Tushare JSON response") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            # Do not expose upstream error text: it may contain request body or token.
            code = payload.get("code") if isinstance(payload, dict) else None
            code = code if type(code) is int else "invalid"
            raise SourceError(f"Tushare API failed (code={code})")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise SourceError("Tushare response missing data")
        fields, items = data.get("fields"), data.get("items")
        if not isinstance(fields, list) or not isinstance(items, list):
            raise SourceError("Tushare response missing fields/items")
        if len(items) >= 6000:
            raise SourceError("Tushare result hit 6000-row cap; split the date window")
        if len(set(fields)) != len(fields) or any(not isinstance(f, str) for f in fields):
            raise SourceError("invalid Tushare result fields")
        rows = []
        for values in items:
            if not isinstance(values, list) or len(values) != len(fields):
                raise SourceError("malformed Tushare result row")
            rows.append(dict(zip(fields, values)))
        return rows


def query_partitioned(source: TushareClient, api_name: str, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    """Split multi-decade backfills so a 6000-row Tushare response is not truncated."""
    rows = []
    cursor = start
    while cursor <= end:
        upper = min(cursor + timedelta(days=3500), end)
        rows.extend(source.query(
            api_name, ts_code=symbol,
            start_date=cursor.strftime("%Y%m%d"), end_date=upper.strftime("%Y%m%d"),
        ))
        cursor = upper + timedelta(days=1)
    return rows


def daily_rows(source: TushareClient, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    validate_symbol(symbol)
    if start > end:
        raise ValueError("start after end")
    raw = query_partitioned(source, "daily", symbol, start, end)
    result: dict[str, dict[str, Any]] = {}
    for row in raw:
        if row.get("ts_code") != symbol:
            raise SourceError("Tushare returned unexpected daily symbol")
        d = parse_day(row["trade_date"])
        if not start <= d <= end:
            raise SourceError("daily trade_date outside requested range")
        prices = {k: valid_number(row[k], positive=True) for k in ("open", "high", "low", "close")}
        vol = valid_number(row["vol"])
        amt = valid_number(row["amount"])
        if vol < 0 or amt < 0 or prices["high"] < max(prices["open"], prices["close"], prices["low"]) or prices["low"] > min(prices["open"], prices["close"], prices["high"]):
            raise SourceError("invalid OHLC or volume/amount")
        key = d.isoformat()
        if key in result:
            raise SourceError("duplicate daily date")
        result[key] = {
            "ts_code": symbol, "trade_date": key, **prices,
            "vol": vol * 100,        # source hands -> TSP shares
            "amt": amt * 1000,       # source thousand CNY -> TSP CNY
        }
    return [result[k] for k in sorted(result)]


def factor_snapshots(source: TushareClient, symbol: str, start: date, end: date) -> dict[str, float]:
    validate_symbol(symbol)
    raw = query_partitioned(source, "adj_factor", symbol, start, end)
    result: dict[str, float] = {}
    for row in raw:
        if row.get("ts_code") != symbol:
            raise SourceError("unexpected adjustment-factor symbol")
        d = parse_day(row["trade_date"])
        if not start <= d <= end:
            raise SourceError("adjustment-factor date outside requested range")
        key = d.isoformat()
        if key in result:
            raise SourceError("duplicate adjustment-factor date")
        result[key] = valid_number(row["adj_factor"], positive=True)
    return result


def tsp_factor_events(
    source: TushareClient, symbol: str, start: date, end: date,
    *, allow_initial_baseline: bool = False,
) -> list[dict[str, Any]]:
    """Convert cumulative series to discrete event ratio.

    Always acquire a date before the requested range to avoid a false ex-date.
    Fail closed when the prior snapshot is missing; never assume factor=1.
    """
    earlier = start - timedelta(days=60)
    snapshots = factor_snapshots(source, symbol, earlier, end)
    prior: float | None = None
    result = []
    for day, current in sorted(snapshots.items()):
        if day < start.isoformat():
            prior = current
            continue
        if prior is None:
            if allow_initial_baseline:
                prior = current
                continue
            raise SourceError("no pre-window factor baseline; backfill an earlier snapshot")
        ratio = current / prior
        if not math.isclose(ratio, 1.0, rel_tol=1e-8, abs_tol=1e-9):
            result.append({"ts_code": symbol, "trade_date": day, "factor": ratio})
        prior = current
    return result
