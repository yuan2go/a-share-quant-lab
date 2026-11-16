import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, date, timezone

MODULE = (
    Path(__file__).resolve().parents[1] / "integrations/tsp/tushare_source/normalize.py"
)
spec = importlib.util.spec_from_file_location("tsp_normalize", MODULE)
norm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(norm)


class TspSourceUnitsTests(unittest.TestCase):
    def test_financial_revision_is_a_whole_report_not_column_fill(self):
        old = {
            "symbol": "000001.SZ",
            "period_end": date(2026, 9, 30),
            "announce_date": date(2026, 10, 20),
            "value": 1,
            "optional": 2,
        }
        new = {**old, "announce_date": date(2026, 10, 30), "value": 3, "optional": None}
        result = norm.latest_reports([old, new])
        self.assertEqual(result, [new])
        updated = {**new, "_update_flag": "1", "value": 4}
        result = norm.latest_reports([new, updated])
        self.assertEqual(result[0]["value"], 4)
        self.assertNotIn("_update_flag", result[0])

    def test_completed_day_survives_midnight_and_uses_cst_cutoff(self):
        self.assertEqual(
            norm.completed_calendar_day(
                datetime(2026, 11, 16, 16, 1, tzinfo=timezone.utc)
            ),
            date(2026, 11, 16),
        )
        self.assertEqual(
            norm.completed_calendar_day(
                datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
            ),
            date(2026, 11, 17),
        )

    def test_undated_realtime_cannot_reach_native_daily_writer(self):
        row = {
            "ts_code": "000001.SZ",
            "pre_close": 10,
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10,
            "vol": 100,
            "amount": 1000,
        }
        with self.assertLogs("tsp_normalize", level="WARNING"):
            self.assertEqual(norm.realtime([row], require_timestamp=True), [])
        row["trade_time"] = "2026-11-16 15:00:00"
        self.assertEqual(
            norm.realtime([row], require_timestamp=True)[0]["timestamp"], 1794812400000
        )

    def test_daily_and_realtime_have_same_tsp_units(self):
        d = norm.daily(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20261116",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "vol": 100,
                    "amount": 100,
                }
            ]
        )[0]
        rt = norm.realtime(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "sample",
                    "pre_close": 10,
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "vol": 10000,
                    "amount": 100000,
                }
            ]
        )[0]
        self.assertEqual(d["volume"], 100)
        self.assertEqual(d["amount"], 100000)
        self.assertEqual(rt["volume"], d["volume"])
        self.assertEqual(rt["amount"], d["amount"])
        self.assertIsNone(rt["timestamp"])
        self.assertEqual(d["amount"] / d["volume"] / 100, 10)

    def test_cumulative_factors_become_events(self):
        rows = [
            {"ts_code": "000001.SZ", "trade_date": "20260102", "adj_factor": 2},
            {"ts_code": "000001.SZ", "trade_date": "20260105", "adj_factor": 4},
            {"ts_code": "000001.SZ", "trade_date": "20260106", "adj_factor": 4},
        ]
        events = norm.events(rows, norm.day("20260105"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ex_factor"], 2)

    def test_streamed_factor_events_equal_full_history(self):
        rows = [
            {"ts_code": "000001.SZ", "trade_date": d, "adj_factor": f}
            for d, f in [("20260102", 2), ("20260105", 4), ("20260106", 4)]
        ]
        previous = {}
        stream = []
        for row in rows:
            stream.extend(norm.events([row], norm.day("20260105"), previous))
        self.assertEqual(stream, norm.events(rows, norm.day("20260105")))

    def test_duplicate_and_invalid_source_fail(self):
        r = {
            "ts_code": "000001.SZ",
            "trade_date": "20261116",
            "open": 10,
            "high": 9,
            "low": 8,
            "close": 10,
            "vol": 100,
            "amount": 100,
        }
        with self.assertRaises(ValueError):
            norm.daily([r])
        r["high"] = 11
        with self.assertRaises(ValueError):
            norm.daily([r, r])

    def test_zero_trading_row_is_excluded_but_positive_volume_still_fails(self):
        row = {
            "ts_code": "000001.SZ",
            "trade_date": "20261116",
            "open": 0,
            "high": 0,
            "low": 0,
            "close": 10,
            "vol": 0,
            "amount": 0,
        }
        with self.assertLogs("tsp_normalize", level="WARNING"):
            self.assertEqual(norm.daily([row]), [])
        row["close"] = 0
        with self.assertLogs("tsp_normalize", level="WARNING"):
            self.assertEqual(norm.daily([row]), [])
        row["high"] = 10
        row["low"] = 9
        row["close"] = 10
        with self.assertLogs("tsp_normalize", level="WARNING"):
            self.assertEqual(norm.daily([row]), [])
        row["vol"] = 1
        with self.assertRaises(ValueError):
            norm.daily([row])
