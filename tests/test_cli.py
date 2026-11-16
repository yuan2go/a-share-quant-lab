import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_quant_lab.cli import main
from test_contracts import example_batch


class CLITests(unittest.TestCase):
    def test_status_does_not_claim_local_readiness(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(["status"])
        self.assertEqual(status, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["stage"], "retrospective-research-runner")
        self.assertFalse(report["local_run_checked"])
        self.assertIn("historical-PIT", report["not_verified"])

    def test_artifact_validation_reports_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(example_batch()), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main(["validate-artifact", str(path)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["candidate_count"], 1)

    def test_missing_qlib_directory_is_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status = main([
                    "probe-qlib",
                    "--provider-uri", str(missing),
                    "--instrument", "SH600519",
                    "--start", "2025-01-01",
                    "--end", "2025-02-01",
                ])
            self.assertEqual(status, 2)
            self.assertIn("does not exist", err.getvalue())


if __name__ == "__main__":
    unittest.main()
