import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ashare_quant_lab.first_study import StudyError, run_first_qlib_study
from ashare_quant_lab.qlib_dump import dump_parquet_using_official_qlib
from ashare_quant_lab.market_export import _parquet_rows
from ashare_quant_lab.tushare_source import SourceError

CONFIG = {
    "train": ["2019-01-02", "2022-12-09"],
    "valid": ["2023-01-03", "2023-12-08"],
    "test": ["2024-01-03", "2026-09-30"],
    "horizon": 10,
    "min_cross_section": 10,
}


class QlibLineageTests(unittest.TestCase):
    def test_changed_parquet_rejected_before_official_converter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = root / "official" / "scripts" / "dump_bin.py"
            official.parent.mkdir(parents=True)
            official.write_text("# converter must never execute\n", encoding="utf-8")
            snapshot = root / "snapshot"
            snapshot.mkdir()
            raw_bytes = b"synthetic-parquet-bytes"
            (snapshot / "SH600519.parquet").write_bytes(raw_bytes)
            manifest = {
                "schema_version": 2, "file_format": "parquet",
                "point_in_time_status": "RETROSPECTIVE_ONLY",
                "files": [{"file": "SH600519.parquet", "sha256": hashlib.sha256(raw_bytes).hexdigest()}],
            }
            (snapshot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (snapshot / "SH600519.parquet").write_bytes(b"tampered")
            with self.assertRaisesRegex(SourceError, "differ"):
                dump_parquet_using_official_qlib(root / "official", snapshot, root / "binary")
            self.assertFalse((root / "binary").exists())

    def test_runner_requires_qlib_dataset_lineage(self):
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
            (provider / "aql_source_manifest.json").write_text(json.dumps({"source_manifest_sha256": "wrong"}))
            with self.assertRaisesRegex(StudyError, "snapshot IDs disagree"):
                run_first_qlib_study(provider, manifest, config, root / "result")

    def test_zero_volume_does_not_invent_vwap(self):
        bars = [{
            "trade_date": date(2020, 1, 2), "open": 10.0,
            "high": 10.0, "low": 10.0, "close": 10.0,
            "volume_shares": 0, "amount_cny": 0,
            "cumulative_factor": 1.0,
        }]
        with self.assertRaisesRegex(SourceError, "factor/volume/amount"):
            _parquet_rows(bars)


if __name__ == "__main__":
    unittest.main()
