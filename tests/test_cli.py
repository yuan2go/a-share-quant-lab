import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_quant_lab.cli import main
from test_contracts import example_batch


class CLITests(unittest.TestCase):
    def test_status_reports_implementation_not_live_validation(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(["status"])
        self.assertEqual(status, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["stage"], "adapter-implementation_not_live_validated")
        self.assertIn("qlib-model-execution", report["not_verified"])

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
