"""Real DuckDB and Parquet integration tests against synthetic market records."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from ashare_quant_lab.market_ingest import ingest_market
from ashare_quant_lab.market_store import (
    connect_store, latest_bars, latest_capture_status,
    read_tsp_daily, read_tsp_factor_events,
)
from ashare_quant_lab.market_export import export_market_parquet
from ashare_quant_lab.tsp_gateway import handle_request
from ashare_quant_lab.tushare_source import SourceError


class FakeTushare:
    def __init__(self, last_close=52.0, *, fail_factors=False):
        self.last_close = last_close
        self.fail_factors = fail_factors

    def query(self, api_name, **kwargs):
        if api_name == "trade_cal":
            start = date.fromisoformat(f"{kwargs['start_date'][:4]}-{kwargs['start_date'][4:6]}-{kwargs['start_date'][6:8]}")
            end = date.fromisoformat(f"{kwargs['end_date'][:4]}-{kwargs['end_date'][4:6]}-{kwargs['end_date'][6:8]}")
            rows = []
            day = start
            while day <= end:
                rows.append({"cal_date": day.strftime("%Y%m%d"), "is_open": 1 if day.weekday() < 5 else 0})
                day += timedelta(days=1)
            return rows
        if api_name == "adj_factor":
            if self.fail_factors:
                return []
            rows = [
                {"ts_code": "600519.SH", "trade_date": "20260105", "adj_factor": 1.0},
                {"ts_code": "600519.SH", "trade_date": "20260106", "adj_factor": 2.0},
            ]
        elif api_name == "daily":
            rows = [
                {"ts_code": "600519.SH", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 103, "vol": 100, "amount": 1000},
                {"ts_code": "600519.SH", "trade_date": "20260106", "open": 50, "high": 54, "low": 49, "close": self.last_close, "vol": 200, "amount": 1010},
            ]
        else:
            raise AssertionError("unexpected source API")
        return [row for row in rows if kwargs["start_date"] <= row["trade_date"] <= kwargs["end_date"]]


class MarketStoreTests(unittest.TestCase):
    def test_ingest_export_and_tsp_read_are_consistent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db_path = root / "market.duckdb"
            first = ingest_market(db_path, FakeTushare(), ["600519.SH"], date(2026, 1, 5), date(2026, 1, 6))
            self.assertEqual(first["daily_rows"], 2)
            self.assertEqual(latest_capture_status(db_path)["latest_complete"]["rows"], 2)
            with connect_store(db_path, read_only=True) as conn:
                raw = read_tsp_daily(conn, "600519.SH", date(2026, 1, 5), date(2026, 1, 6))
                self.assertEqual(raw[0]["vol"], 10000.0)  # shares
                self.assertEqual(raw[0]["amt"], 1_000_000.0)  # CNY
                self.assertEqual(
                    read_tsp_factor_events(conn, "600519.SH", date(2026, 1, 5), date(2026, 1, 6)),
                    [{"ts_code": "600519.SH", "trade_date": "2026-01-06", "factor": 2.0}],
                )
                response = handle_request(conn, "/daily", {
                    "symbols": ["600519.SH"], "start_time": "2026-01-05", "end_time": "2026-01-06",
                })
                self.assertEqual(response["data"][1]["close"], 52.0)

            snapshot = root / "frozen"
            result = export_market_parquet(
                db_path, ["600519.SH"], date(2026, 1, 5), date(2026, 1, 6),
                snapshot, min_history=2,
            )
            self.assertEqual(result["rows"], 2)
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["file_format"], "parquet")
            self.assertEqual(manifest["source_capture_ids"], [first["capture_id"]])
            with connect_store(db_path, read_only=True) as conn:
                values = conn.execute(
                    f"SELECT close, volume, amount, factor FROM read_parquet('{snapshot / 'SH600519.parquet'}') ORDER BY date"
                ).fetchall()
            self.assertEqual(values[1][0], 104.0)  # adjusted 52 * 2
            self.assertEqual(values[1][1], 10000.0)  # 200 * 100 / 2
            self.assertEqual(values[1][2], 1_010_000.0)  # amount is not adjusted
            self.assertEqual(values[1][3], 2.0)
            with self.assertRaises(FileExistsError):
                export_market_parquet(
                    db_path, ["600519.SH"], date(2026, 1, 5), date(2026, 1, 6),
                    snapshot, min_history=2,
                )

    def test_latest_completed_capture_wins_and_failed_capture_is_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "market.duckdb"
            start, end = date(2026, 1, 5), date(2026, 1, 6)
            ingest_market(db_path, FakeTushare(52.0), ["600519.SH"], start, end)
            with self.assertRaisesRegex(SourceError, "coverage"):
                ingest_market(db_path, FakeTushare(fail_factors=True), ["600519.SH"], start, end)
            self.assertEqual(latest_capture_status(db_path)["capture_counts"], {"COMPLETE": 1, "FAILED": 1})
            with connect_store(db_path, read_only=True) as conn:
                self.assertEqual(latest_bars(conn, "600519.SH", start, end)[-1]["close"], 52.0)
            ingest_market(db_path, FakeTushare(53.0), ["600519.SH"], start, end)
            with connect_store(db_path, read_only=True) as conn:
                self.assertEqual(latest_bars(conn, "600519.SH", start, end)[-1]["close"], 53.0)


    def test_refuses_to_modify_non_aql_duckdb_database(self):
        import duckdb
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foreign.duckdb"
            foreign = duckdb.connect(str(path))
            foreign.execute("CREATE TABLE unrelated_data (x INTEGER)")
            foreign.close()
            with self.assertRaisesRegex(SourceError, "not an AQL"):
                with connect_store(path):
                    pass
            check = duckdb.connect(str(path), read_only=True)
            try:
                names = {row[0] for row in check.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()}
                self.assertIn("unrelated_data", names)
                self.assertNotIn("captures", names)
            finally:
                check.close()


if __name__ == "__main__":
    unittest.main()
