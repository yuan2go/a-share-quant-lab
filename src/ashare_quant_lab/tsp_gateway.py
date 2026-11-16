"""TSP read-only local DuckDB historical-data gateway.

No Tushare credential or external network request occurs on TSP page access.
DuckDB is a single-writer database; stop this process when ingesting from a
separate Python process. The serving copy remains TSP's own storage.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .market_store import (
    connect_store, latest_capture_status, read_tsp_daily, read_tsp_factor_events,
)
from .tushare_source import SourceError, parse_day, validate_symbol


def handle_request(conn, path: str, body: object) -> dict:
    if path not in ("/daily", "/adj_factor"):
        raise ValueError("unsupported dataset")
    if not isinstance(body, dict):
        raise ValueError("expected JSON object")
    symbols = body.get("symbols")
    if isinstance(symbols, str):
        symbols = [s for s in symbols.split(",") if s]
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols):
        raise ValueError("symbols must contain 1–10 distinct A-share codes")
    for symbol in symbols:
        validate_symbol(symbol)
    if body.get("asset_type") not in (None, "stock"):
        raise ValueError("only asset_type=stock is supported")

    start = parse_day(body["start_time"]) if body.get("start_time") else date(1990, 1, 1)
    today_cn = datetime.now(timezone(timedelta(hours=8))).date()
    end = parse_day(body["end_time"]) if body.get("end_time") else today_cn
    if start > end or (end - start).days > 15000:
        raise ValueError("invalid date range")

    rows = []
    for symbol in symbols:
        if path == "/daily":
            rows.extend(read_tsp_daily(conn, symbol, start, end))
        else:
            rows.extend(read_tsp_factor_events(conn, symbol, start, end))
    return {
        "data": rows,
        "source": "aql-duckdb-complete-captures",
        "asset_type": "stock",
        "units": {"vol": "hands_100_shares", "amt": "CNY", "factor": "single_event_ratio"},
        "historical_PIT_qualified": False,
    }


def make_handler(db_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, obj: dict):
            data = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/health":
                self._json(404, {"error": "unknown path"})
                return
            try:
                state = latest_capture_status(db_path)
                if state["latest_complete"] is None:
                    self._json(503, {"status": "NO_COMPLETE_CAPTURE"})
                else:
                    self._json(200, {"status": "LOCAL_HISTORICAL_DATA_AVAILABLE",
                                     "latest_capture": state["latest_complete"],
                                     "historical_PIT_qualified": False})
            except (SourceError, OSError):
                self._json(503, {"status": "MARKET_DATABASE_UNAVAILABLE"})

        def do_POST(self):
            if self.path not in ("/daily", "/adj_factor"):
                self._json(404, {"error": "unknown path"})
                return
            length = self.headers.get("Content-Length", "")
            try:
                if not length.isdecimal() or not 0 < int(length) <= 20000:
                    raise ValueError("invalid request length")
                body = json.loads(self.rfile.read(int(length)))
                with connect_store(db_path, read_only=True) as conn:
                    self._json(200, handle_request(conn, self.path, body))
            except (ValueError, KeyError, TypeError):
                self._json(422, {"error": "invalid request: check symbols/date/type"})
            except (SourceError, OSError):
                self._json(503, {"error": "market database unavailable or not fully ingested"})

        def log_message(self, fmt, *args):
            # No SQL, source token, security identifiers or input payload in logs.
            return
    return Handler


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Local DuckDB -> TSP daily/adj_factor gateway")
    parser.add_argument("--db-path", type=Path, default=Path("data/market.duckdb"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-lan", action="store_true",
                        help="Explicitly allow nonloopback binding; secure with firewall")
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "::1", "localhost") and not args.allow_lan:
        print("refusing unauthenticated nonloopback binding without --allow-lan", file=sys.stderr)
        return 2
    try:
        if latest_capture_status(args.db_path)["latest_complete"] is None:
            raise SourceError("no complete market-data capture exists")
    except (SourceError, OSError) as exc:
        print(f"TSP gateway not ready: {exc}", file=sys.stderr)
        return 2

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.db_path))
    print(f"Read-only historical gateway on {args.host}:{args.port}; no external data fetch", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
