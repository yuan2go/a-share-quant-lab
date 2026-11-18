"""Exercise the final fit, independent calibration and mature frequency clocks."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(importlib.util.find_spec("qlib"), "requires native dataset processing")
class RefitTests(unittest.TestCase):
    def test_only_final_model_scores_the_held_out_calibration_window(self):
        import numpy as np
        import pandas as pd
        from qlib.data.dataset.handler import DataHandlerLP
        from ashare_quant_lab.direction_data import monthly_split
        from ashare_quant_lab.direction_study import train_month

        config = json.loads(
            (Path(__file__).resolve().parents[1] / "configs/direction-refit.json").read_text()
        )
        cal = pd.bdate_range("2018-01-02", periods=1200)
        split = monthly_split(cal, cal[-1], config)
        idx = pd.MultiIndex.from_product([cal, ["SH600519"]], names=["datetime", "instrument"])
        up = np.arange(len(cal)) % 3 == 0
        raw = pd.DataFrame(
            {("feature", "X"): up.astype(float), ("label", "RETURN"): np.where(up, 0.1, -0.1)}, index=idx
        )
        # A missing mature endpoint remains outside the smoothed frequency denominator.
        raw.loc[split["calibration"][0], ("label", "RETURN")] = np.nan
        eligible = pd.Series(True, index=idx)
        momentum = pd.Series(np.linspace(-0.1, 0.1, len(cal)), index=idx)
        selector, final = Mock(), Mock()
        selector.model.best_iteration = 7
        final.model.save_model.side_effect = lambda path: Path(path).write_text("synthetic final model")

        def score(dataset, segment):
            x = dataset.prepare(segment, col_set="feature", data_key=DataHandlerLP.DK_I).iloc[:, 0]
            return 0.25 + 0.5 * x

        final.predict.side_effect = score
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "ashare_quant_lab.direction_study.native_model_fit", side_effect=[selector, final]
            ) as fit,
        ):
            fitted, record = train_month(
                raw,
                eligible,
                momentum,
                cal,
                cal[-1],
                config,
                Path(directory) / "model",
                {},
                {"lookback": 60},
            )
        self.assertIs(fitted, final)
        selector.predict.assert_not_called()
        self.assertEqual(fit.call_args_list[1].args[1], 7)
        final_data = fit.call_args_list[1].args[0]
        self.assertEqual(set(final_data.segments), {"train"})
        refit = final_data.prepare("train", col_set="label", data_key=DataHandlerLP.DK_L)
        days = refit.index.get_level_values("datetime")
        self.assertEqual(days.nunique(), 756)
        self.assertEqual(str(days.max().date()), split["valid"][1])
        self.assertLess(cal[cal.get_loc(days.max()) + 11], pd.Timestamp(split["calibration"][0]))
        cal_days = cal[(cal > split["calibration"][0]) & (cal <= split["calibration"][1])]
        self.assertEqual(record["calibrator"]["fit_rows"], len(cal_days))
        self.assertGreater(record["calibrator"]["coefficient"], 0)
        self.assertEqual(
            record["baseline_recent"], (up[cal.get_indexer(cal_days)].sum() + 1) / (len(cal_days) + 2)
        )
