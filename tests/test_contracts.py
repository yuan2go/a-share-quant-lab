import copy
import unittest

from ashare_quant_lab.contracts import (
    ArtifactValidationError,
    validate_prediction_batch,
)


def example_batch():
    # Pure fixture: not a prediction or financial research result.
    return {
        "schema_version": 1,
        "run_id": "fixture-structural-validation",
        "created_at": "2026-11-16T16:00:00+08:00",
        "signal_cutoff": "2026-11-16T15:05:00+08:00",
        "market": "CN-A",
        "forecast_horizon_days": 10,
        "model_id": "fixture-model-not-trained",
        "universe_id": "fixture-universe-not-qualified",
        "data_snapshot_id": "fixture-data-not-real",
        "predictions": [{"symbol": "600519.SH", "score": 0.5}],
    }


class PredictionContractTests(unittest.TestCase):
    def test_valid_batch(self):
        batch = example_batch()
        self.assertIs(validate_prediction_batch(batch), batch)

    def test_zero_candidates_is_valid(self):
        batch = example_batch()
        batch["predictions"] = []
        self.assertEqual(validate_prediction_batch(batch)["predictions"], [])

    def test_duplicate_symbol_is_rejected(self):
        batch = example_batch()
        batch["predictions"].append(copy.deepcopy(batch["predictions"][0]))
        with self.assertRaisesRegex(ArtifactValidationError, "duplicate"):
            validate_prediction_batch(batch)

    def test_nan_is_rejected(self):
        batch = example_batch()
        batch["predictions"][0]["score"] = float("nan")
        with self.assertRaises(ArtifactValidationError):
            validate_prediction_batch(batch)

    def test_timezones_required(self):
        batch = example_batch()
        batch["signal_cutoff"] = "2026-11-16T15:05:00"
        with self.assertRaisesRegex(ArtifactValidationError, "timezone"):
            validate_prediction_batch(batch)

    def test_future_cutoff_rejected(self):
        batch = example_batch()
        batch["created_at"] = "2026-11-16T14:00:00+08:00"
        with self.assertRaisesRegex(ArtifactValidationError, "precede"):
            validate_prediction_batch(batch)

    def test_bool_cannot_be_a_score(self):
        batch = example_batch()
        batch["predictions"][0]["score"] = True
        with self.assertRaises(ArtifactValidationError):
            validate_prediction_batch(batch)

    def test_instrument_shape(self):
        batch = example_batch()
        batch["predictions"][0]["symbol"] = "SH600519"
        with self.assertRaisesRegex(ArtifactValidationError, "NNNNNN"):
            validate_prediction_batch(batch)

    def test_bool_cannot_be_schema_version(self):
        batch = example_batch()
        batch["schema_version"] = True
        with self.assertRaisesRegex(ArtifactValidationError, "schema_version"):
            validate_prediction_batch(batch)


if __name__ == "__main__":
    unittest.main()
