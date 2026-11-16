import json
import tempfile
import unittest
from pathlib import Path

from ashare_quant_lab.tsp_publish import publish_to_tsp
from test_contracts import example_batch


class PublishTests(unittest.TestCase):
    def test_matching_study_is_published_only_to_explicit_local_dir(self):
        with tempfile.TemporaryDirectory() as d:
            study = Path(d) / "study"
            study.mkdir()
            tsp_data = Path(d) / "tsp_data"
            tsp_data.mkdir()
            batch = example_batch()
            (study / "prediction-batch.json").write_text(json.dumps(batch), encoding="utf-8")
            (study / "study-report.json").write_text(json.dumps({
                "run_id": batch["run_id"],
                "status": "RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED"
            }), encoding="utf-8")
            result = publish_to_tsp(study, tsp_data)
            self.assertEqual(result["tsp_running_verified"], False)
            self.assertEqual(json.loads((tsp_data / "aql" / "latest-prediction.json").read_text())["run_id"], batch["run_id"])

    def test_mismatched_report_fails(self):
        with tempfile.TemporaryDirectory() as d:
            study = Path(d) / "study"
            study.mkdir()
            data = Path(d) / "tsp"
            data.mkdir()
            (study / "prediction-batch.json").write_text(json.dumps(example_batch()))
            (study / "study-report.json").write_text(json.dumps({"run_id": "wrong", "status":"RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED"}))
            with self.assertRaisesRegex(ValueError, "run_id"):
                publish_to_tsp(study, data)


if __name__ == "__main__":
    unittest.main()
