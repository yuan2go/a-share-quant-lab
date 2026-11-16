import tempfile
import unittest
from datetime import date
from pathlib import Path

from ashare_quant_lab.qlib_export import (
    build_adjusted_csv_rows,
    export_qlib_csv,
    qlib_to_symbol,
    symbol_to_qlib,
)
from ashare_quant_lab.first_study import StudyError, validate_study_config
from ashare_quant_lab.tushare_source import SourceError


class FakeSource:
    def query(self, name, **kwargs):
        if name == "daily":
            return [
                {"ts_code": "600519.SH", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 103, "vol": 100, "amount": 1000},
                {"ts_code": "600519.SH", "trade_date": "20260106", "open": 50, "high": 54, "low": 49, "close": 52, "vol": 200, "amount": 1010},
            ]
        if name == "adj_factor":
            return [
                {"ts_code": "600519.SH", "trade_date": "20260105", "adj_factor": 1},
                {"ts_code": "600519.SH", "trade_date": "20260106", "adj_factor": 2},
            ]
        raise AssertionError(name)


class ExportTests(unittest.TestCase):
    def test_export_adjusts_prices_volume_not_amount(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "snapshot"
            summary = export_qlib_csv(FakeSource(), ["600519.SH"], date(2026, 1, 5), date(2026, 1, 6), output)
            self.assertEqual(summary["rows"], 2)
            lines = (output / "SH600519.csv").read_text().splitlines()
            self.assertIn("104.0", lines[-1])  # raw 52 * cumulative ratio 2
            self.assertIn("10000.0", lines[-1])  # raw 200 hands -> 20000 shares / 2
            self.assertEqual(qlib_to_symbol(symbol_to_qlib("600519.SH")), "600519.SH")
            with self.assertRaises(FileExistsError):
                export_qlib_csv(FakeSource(), ["600519.SH"], date(2026, 1, 5), date(2026, 1, 6), output)

    def test_missing_factor_blocks_data(self):
        with self.assertRaisesRegex(SourceError, "coverage"):
            build_adjusted_csv_rows([{"trade_date": "2026-01-05"}], {})

    def test_explicit_time_embargo_guard(self):
        c = {"train": ["2021-01-01", "2022-12-01"], "valid": ["2023-01-01", "2023-12-01"], "test": ["2024-01-01", "2024-11-01"], "horizon": 10, "min_cross_section": 5}
        with self.assertRaisesRegex(StudyError, "embargo"):
            validate_study_config(c, [date(2022, 12, 2), date(2023, 1, 1), date(2023, 12, 2), date(2024, 1, 1), date(2024, 11, 2)])


if __name__ == "__main__":
    unittest.main()
