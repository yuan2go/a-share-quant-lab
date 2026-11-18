"""Risk-targeted checks for paired, revision-aware natural forecasts."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from ashare_quant_lab.direction_data import write_json


@unittest.skipUnless(importlib.util.find_spec("pandas"), "requires research environment")
class ForwardArchiveTests(unittest.TestCase):
    def test_only_first_eligible_issuance_and_verified_maturity_per_day(self):
        from copy import deepcopy
        from ashare_quant_lab.direction_data import EVENT, digest
        from ashare_quant_lab.direction_forward import CONFIG, CORE, issuance, summarize
        from ashare_quant_lab.symbols import load_symbols

        symbols = load_symbols(CONFIG / "first-study-cohort.txt")
        predictions = [
            dict(symbol=s, data_quality="FULL_RAW_LOOKBACK", **{n + "_probability": 0.5 for n in CORE})
            for s in symbols
        ]
        batch = dict(
            kind="DIRECTION_PREDICTION",
            schema_version=2,
            work_package="test",
            up_event=EVENT,
            status="CURRENT_COMPLETED_SESSION_RESEARCH_ONLY",
            generated_at="2026-11-17T16:30:00+08:00",
            data_through="2026-11-17",
            expected_latest_completed_session="2026-11-17",
            prediction_interval=dict(start_date="2026-11-18", end_date="2026-12-02"),
            snapshot_exported_at="2026-11-17T16:20:00+08:00",
            model_id="m",
            inference_snapshot_id="s",
            training_split=dict(anchor="2026-11-02", mature_through="2026-10-30"),
            data_kind="REAL_SOURCE_RETROSPECTIVE",
            issuance_status="ISSUED_BEFORE_TARGET_ENTRY_CLOSE",
            predictions=predictions,
            recent_baseline_applicable=False,
        )
        self.assertEqual(issuance(dict(batch, recent_baseline_applicable=True)), "INCOMPLETE_PROBABILITIES")
        self.assertEqual(issuance(dict(batch, predictions=predictions[:-1])), "INCOMPLETE_COHORT")
        self.assertEqual(issuance(dict(batch, publication_kind="BACKFILL")), "BACKFILL")
        self.assertEqual(
            issuance(dict(batch, generated_at="2026-11-18T15:00:00+08:00")),
            "DELAYED_AFTER_TARGET_ENTRY_CLOSE",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def save(name, data):
                path = root / name
                write_json(path, data)
                return path

            original = save("one", batch)
            later = save("two", dict(batch, generated_at="2026-11-17T17:00:00+08:00"))
            newer = deepcopy(batch)
            newer.update(
                data_through="2026-11-18",
                expected_latest_completed_session="2026-11-18",
                generated_at="2026-11-18T16:30:00+08:00",
                recent_baseline_applicable=True,
                prediction_interval=dict(start_date="2026-11-19", end_date="2026-12-03"),
            )
            for p in newer["predictions"]:
                p["recent_probability"] = 0.6
            day2 = save("three", newer)
            review = dict(
                kind="DIRECTION_MATURITY_REVIEW",
                model_id="m",
                original_inference_snapshot_id="s",
                prediction_sha256=digest(original),
                data_through="2026-12-03",
                status="MATURE_REVIEW",
                reviewed_at="2026-12-03T17:00:00+08:00",
                review_capture_started_at="2026-12-03T16:00:00+08:00",
                review_capture_completed_at="2026-12-03T16:10:00+08:00",
                review_data_kind="REAL_SOURCE_RETROSPECTIVE",
                labels=[dict(symbol=s, y=1, **{"return": 0.01}) for s in symbols],
            )
            mature = save("mature", review)
            revision = save(
                "revision",
                dict(
                    review,
                    reviewed_at="2026-12-04T17:00:00+08:00",
                    labels=[dict(symbol=s, y=0, **{"return": 0.0}) for s in symbols],
                ),
            )
            synthetic = save("synthetic", dict(review, review_data_kind="SYNTHETIC_ENGINEERING_ONLY"))
            early = save("early", dict(review, review_capture_started_at="2026-12-02T14:59:00+08:00"))
            for path in [synthetic, early]:
                name = root / (path.name + "-result")
                self.assertEqual(summarize([original], [path], name)["pairs"], 0)
            second = save("day2", dict(review, prediction_sha256=digest(day2)))
            out = root / "result"
            summarize([original, original, later, day2], [revision, mature, mature, second], out)
            summary = json.loads(out.read_text())
            self.assertEqual(len(summary["batches"]), 3)
            self.assertTrue(summary["batches"][1]["reissue"])
            self.assertEqual(summary["batches"][0]["primary_review"], digest(mature))
            self.assertEqual(summary["paired"]["original_methods"]["pairs"], 60)
            self.assertEqual(summary["paired"]["original_methods"]["dates"], 2)
            self.assertEqual(summary["paired"]["including_recent"]["pairs"], 30)
            self.assertEqual(summary["paired"]["original_methods"]["metrics"]["raw"]["positive_pairs"], 60)
