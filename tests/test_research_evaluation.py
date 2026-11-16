import importlib.util
import unittest

from ashare_quant_lab.research_evaluation import StudyError, canonical_series, paired_rank_ic


@unittest.skipUnless(importlib.util.find_spec('pandas'), 'requires Qlib environment pandas')
class EvaluationTests(unittest.TestCase):
    def test_named_levels_are_reordered_and_constant_day_excluded_for_both(self):
        import pandas as pd
        idx = pd.MultiIndex.from_product([pd.date_range('2024-01-03', periods=3), list('ABCDE')],
                                         names=['datetime', 'instrument'])
        truth = pd.Series(list(range(5)) * 3, index=idx, dtype=float)
        model = truth.copy()
        momentum = -truth
        momentum.loc[pd.Timestamp('2024-01-04')] = 1.0
        momentum = momentum.reorder_levels(['instrument', 'datetime'])
        result, daily, union = paired_rank_ic(model, momentum, truth, 5, min_days=2)
        self.assertEqual(result['days'], 2)
        self.assertEqual(result['pairs'], 10)
        self.assertAlmostEqual(result['difference'], 2.0)
        self.assertEqual(result['excluded_days'][0]['reason'], 'constant_score_or_label')
        self.assertEqual(union.index.names, ['datetime', 'instrument'])

    def test_nonfinite_predictions_and_missing_baseline_share_one_denominator(self):
        import pandas as pd
        idx = pd.MultiIndex.from_product([pd.date_range('2024-01-03', periods=2), list('ABCDEF')],
                                         names=['datetime', 'instrument'])
        truth = pd.Series(list(range(6)) * 2, index=idx, dtype=float)
        model, momentum = truth.copy(), -truth
        model.iloc[0] = float('inf')
        momentum = momentum.drop(idx[7])
        result, _, _ = paired_rank_ic(model, momentum, truth, 5, min_days=2)
        self.assertEqual(result['common_finite_pairs'], 10)
        self.assertEqual(result['pairs'], 10)
        self.assertEqual(result['excluded_nonfinite_or_missing_pairs'], 2)

    def test_duplicate_and_unnamed_indices_fail_closed(self):
        import pandas as pd
        idx = pd.MultiIndex.from_tuples([('2024-01-03', 'SH600519')] * 2,
                                       names=['datetime', 'instrument'])
        with self.assertRaisesRegex(StudyError, 'duplicate'):
            canonical_series(pd.Series([1, 2], index=idx), 'model')
        idx = idx.set_names([None, None])
        with self.assertRaisesRegex(StudyError, 'levels'):
            canonical_series(pd.Series([1, 2], index=idx), 'model')
