"""Local, read-only TSP daily/adjustment HTTP adapter for a Tushare proxy.

Do not expose beyond a trusted local network. No auth token in HTTP response,
URL, YAML, source code or repository. No realtime service is advertised.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .tushare_source import SourceError, TushareClient, daily_rows, parse_day, tsp_factor_events, validate_symbol


def handle_request(source: TushareClient, path: str, body: object) -> dict:
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
        # Explicitly unsupported; do not silently return stock data as ETF/index.
        raise ValueError("only asset_type=stock is supported")
    if not body.get("start_time") or not body.get("end_time"):
        raise ValueError("start_time and end_time required; refuse implicit partial history")
    start, end = parse_day(body["start_time"]), parse_day(body["end_time"])
    if start > end or (end - start).days > 5500:
        raise ValueError("invalid range or >5500 days; split backfill windows")
    rows = []
    for symbol in symbols:
        rows.extend(daily_rows(source, symbol, start, end) if path == "/daily" else tsp_factor_events(source, symbol, start, end))
    return {"data": rows, "source": "tushare-http", "asset_type": "stock"}


def make_handler(source: TushareClient):
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
            if self.path == "/health":
                self._json(200, {"status": "ready", "scope": ["daily", "adj_factor"], "data_verified": False})
            else:
                self._json(404, {"error": "unknown path"})

        def do_POST(self):
            length = self.headers.get("Content-Length", "")
            if self.path not in ("/daily", "/adj_factor"):
                self._json(404, {"error": "unknown path"})
                return
            try:
                if not length.isdecimal() or not 0 < int(length) <= 20000:
                    raise ValueError("invalid request length")
                body = json.loads(self.rfile.read(int(length)))
                self._json(200, handle_request(source, self.path, body))
            except (ValueError, KeyError, TypeError):
                self._json(422, {"error": "invalid data request; check symbols/date/type"})
            except SourceError as exc:
                self._json(502, {"error": str(exc)})

        def log_message(self, format, *args):
            # Never log URL queries or request bodies.
            return

    return Handler


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Local Tushare -> TSP daily/adj_factor gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        source = TushareClient()
    except SourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        print("WARNING: non-loopback binding exposes unauthenticated market data; restrict by firewall", file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(source))
    print(f"TSP local historical gateway listening on {args.host}:{args.port} (no realtime)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
