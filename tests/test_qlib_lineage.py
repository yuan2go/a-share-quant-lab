import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ashare_quant_lab.first_study import StudyError, run_first_qlib_study
from ashare_quant_lab.qlib_dump import dump_csv_using_official_qlib
from ashare_quant_lab.qlib_export import build_adjusted_csv_rows
from ashare_quant_lab.tushare_source import SourceError


CONFIG = {
    "train": ["2019-01-02", "2022-12-09"],
    "valid": ["2023-01-03", "2023-12-08"],
    "test": ["2024-01-03", "2026-09-30"],
    "horizon": 10,
    "min_cross_section": 10,
}


class QlibLineageTests(unittest.TestCase):
    def test_changed_csv_is_rejected_before_converter_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_checkout = root / "official-source"
            converter = source_checkout / "scripts" / "dump_bin.py"
            converter.parent.mkdir(parents=True)
            converter.write_text("# placeholder; never executed\n", encoding="utf-8")
            data = root / "csv"
            data.mkdir()
            csv_bytes = b"date,close\n2020-01-02,10\n"
            (data / "SH600519.csv").write_bytes(csv_bytes)
            manifest = {
                "schema_version": 1,
                "files": [{"file": "SH600519.csv", "sha256": hashlib.sha256(csv_bytes).hexdigest()}],
            }
            (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (data / "SH600519.csv").write_text("date,close\n2020-01-02,999\n", encoding="utf-8")
            with self.assertRaisesRegex(SourceError, "differs"):
                dump_csv_using_official_qlib(source_checkout, data, root / "dumped")
            self.assertFalse((root / "dumped").exists())

    def test_runner_requires_source_lineage_before_importing_qlib(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = root / "provider"
            provider.mkdir()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "point_in_time_status": "RETROSPECTIVE_ONLY",
                "universe": ["600519.SH"],
            }), encoding="utf-8")
            config = root / "study.json"
            config.write_text(json.dumps(CONFIG), encoding="utf-8")
            with self.assertRaisesRegex(StudyError, "no source lineage"):
                run_first_qlib_study(provider, manifest, config, root / "result")

            (provider / "aql_source_manifest.json").write_text(
                json.dumps({"source_manifest_sha256": "wrong"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(StudyError, "snapshot IDs disagree"):
                run_first_qlib_study(provider, manifest, config, root / "result")

    def test_zero_volume_does_not_invent_vwap(self):
        bars = [{
            "trade_date": "2020-01-02",
            "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
            "vol": 0, "amt": 0,
        }]
        with self.assertRaisesRegex(SourceError, "VWAP"):
            build_adjusted_csv_rows(bars, {"2020-01-02": 1.0})


if __name__ == "__main__":
    unittest.main()
