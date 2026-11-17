"""Risk-targeted direction protocol tests; native real evidence is stored privately."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ashare_quant_lab.direction_data import direction_labels, monthly_split, write_json
from ashare_quant_lab.direction_evaluation import block_interval, evaluate
from ashare_quant_lab.direction_inference import expected_session
from ashare_quant_lab.research_evaluation import StudyError


@unittest.skipUnless(importlib.util.find_spec('pandas'), 'requires optional research environment')
class DirectionTests(unittest.TestCase):
    def config(self):
        return json.loads((Path(__file__).resolve().parents[1] / 'configs/direction-study.json').read_text())

    def test_positive_negative_zero_missing_stay_distinct(self):
        import numpy as np
        import pandas as pd
        actual = direction_labels(pd.Series([.01, -.01, 0., np.nan, np.inf, -np.inf]))
        self.assertEqual(actual.iloc[:3].tolist(), [1., 0., 0.])
        self.assertTrue(actual.iloc[3:].isna().all())

    def test_calendar_splits_use_label_end_not_signal_cutoff(self):
        import pandas as pd
        cal = pd.bdate_range('2018-01-01', periods=1600).delete([30, 43, 500])
        split = monthly_split(cal, cal[1400], self.config())
        for a, b in [('train', 'valid'), ('valid', 'calibration')]:
            self.assertLess(pd.Timestamp(split['label_end'][a]), pd.Timestamp(split[b][0]))
        self.assertEqual(split['label_end']['calibration'], str(cal[1399].date()))
        for name, size in [('train',756), ('valid',126), ('calibration',126)]:
            start, end = map(pd.Timestamp, split[name])
            self.assertEqual(cal.get_loc(end) - cal.get_loc(start) + 1, size)
        with self.assertRaisesRegex(StudyError, 'insufficient'):
            monthly_split(cal, cal[400], self.config())

    def test_all_up_all_not_up_dates_and_coverage_are_preserved(self):
        import numpy as np
        import pandas as pd
        cal = pd.bdate_range('2024-01-02', periods=60)
        idx = pd.MultiIndex.from_product([cal, ['SH600519', 'SZ002714']], names=['datetime','instrument'])
        rows = pd.DataFrame(index=idx)
        rows['y'] = np.repeat([0,1]*30, 2)
        rows['return'] = np.where(rows.y == 1, .02, 0.)
        for col, p in [('raw', .5),('model', .5),('b0', .5),('b1', .5)]:
            rows[col] = p
        rows['reason'] = 'ELIGIBLE'
        rows.loc[idx[0], 'b1'] = np.nan
        result, daily = evaluate(rows, cal, self.config())
        self.assertEqual(result['dates'], 60)
        self.assertEqual(result['pairs'],119)
        self.assertEqual(result['coverage']['all_up_dates'],30)
        self.assertEqual(result['coverage']['all_not_up_dates'],30)
        self.assertEqual(result['coverage']['zero_return_pairs'],60)
        self.assertEqual(result['own_output_metrics']['model']['pairs'],120)
        self.assertAlmostEqual(result['metrics']['model']['log_loss'],np.log(2))
        self.assertEqual(result['model_minus_baseline']['b0'],0.)
        self.assertEqual(len(daily),60)
        # A single-class segment keeps its main loss; balanced accuracy is undefined.
        from ashare_quant_lab.direction_evaluation import probability_metrics
        one = probability_metrics(rows[rows.y == 1], 'model')
        self.assertIsNone(one['balanced_accuracy'])
        self.assertIsNotNone(one['log_loss'])

    def test_date_equal_loss_does_not_overweight_large_cross_sections(self):
        import numpy as np
        import pandas as pd
        from ashare_quant_lab.direction_evaluation import probability_metrics
        idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-02'),'A'),
              (pd.Timestamp('2024-01-03'),'A'), (pd.Timestamp('2024-01-03'),'B')], names=['datetime','instrument'])
        rows = pd.DataFrame({'y':[1.,1.,1.], 'model':[.1,.9,.9], 'return':[.1,.1,.1]},index=idx)
        self.assertAlmostEqual(probability_metrics(rows,'model')['log_loss'], (-np.log(.1)-np.log(.9))/2)

    def test_blocks_reproduce_and_keep_missing_date_axis(self):
        import numpy as np
        values = np.arange(100)/100
        values[20:24] = np.nan
        a = block_interval(values, block=20, replicates=2000, seed=23)
        self.assertEqual(a,block_interval(values, block=20, replicates=2000, seed=23))
        self.assertEqual(a['axis_dates'],100)
        self.assertEqual(a['observed_dates'],96)
        self.assertLess(a['lower'],a['upper'])

    def test_latest_operational_clock_and_expiry(self):
        clock = {'captured_at':'2026-11-17T08:00:00+00:00','exchanges':'SSE_SZSE_MATCH',
                 'range_start':'2026-10-01','range_end':'2026-12-30',
                 'open_dates':['2026-11-13','2026-11-16','2026-11-17','2026-11-18']}
        now=datetime(2026,11,17,8,30,tzinfo=timezone.utc)
        self.assertEqual(str(expected_session(clock,now)[0].date()),'2026-11-16')
        after=datetime(2026,11,17,11,30,tzinfo=timezone.utc)
        self.assertEqual(str(expected_session(clock,after)[0].date()),'2026-11-17')
        with self.assertRaisesRegex(StudyError,'expired'):
            expected_session(clock, datetime(2026,11,19,8,30,tzinfo=timezone.utc))

    def test_artifacts_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'prediction.json'
            write_json(path, {'original':True})
            with self.assertRaises(FileExistsError):
                write_json(path, {'original':False})
            self.assertEqual(json.loads(path.read_text()),{'original':True})


@unittest.skipUnless(importlib.util.find_spec('qlib'), 'requires official Qlib environment')
class NativeDirectionTests(unittest.TestCase):
    def test_latest_features_survive_missing_future_label_and_binary_learning(self):
        import numpy as np
        import pandas as pd
        from qlib.data.dataset.handler import DataHandlerLP
        from ashare_quant_lab.direction_data import dataset_from_frame
        idx = pd.MultiIndex.from_product([pd.bdate_range('2024-01-02',periods=4),['SH600519']],names=['datetime','instrument'])
        columns=pd.MultiIndex.from_tuples([('feature','M'),('label','RETURN')])
        raw=pd.DataFrame([[1.,.01],[2.,-.01],[3.,0.],[4.,np.nan]],index=idx,columns=columns)
        dataset=dataset_from_frame(raw,{'train':('2024-01-02','2024-01-04'),'test':('2024-01-05','2024-01-05')},learn=True)
        labels=dataset.prepare('train',col_set='label',data_key=DataHandlerLP.DK_L).iloc[:,0]
        self.assertEqual(labels.tolist(),[1.,0.,0.])
        self.assertEqual(len(dataset.prepare('test',col_set='feature',data_key=DataHandlerLP.DK_I)),1)
        self.assertEqual(len(dataset.prepare('test',col_set='label',data_key=DataHandlerLP.DK_L)),0)

@unittest.skipUnless(importlib.util.find_spec('qlib'), 'requires optional Qlib environment')
class ReviewTests(unittest.TestCase):
    def test_mature_review_appends_labels_without_changing_original(self):
        import pandas as pd
        from ashare_quant_lab.direction_data import EVENT, digest
        from ashare_quant_lab.direction_inference import review_direction
        cal = pd.bdate_range('2024-01-02', periods=13)
        idx = pd.MultiIndex.from_product([['SH600519'],cal[1:12]],names=['instrument','datetime'])
        close = pd.DataFrame({'$close':[100.]*10+[101.]},index=idx)
        batch={'kind':'DIRECTION_PREDICTION','up_event':EVENT,'model_id':'model',
               'inference_snapshot_id':'old','data_through':str(cal[0].date()),
               'prediction_interval':{'start_date':str(cal[1].date()),'end_date':str(cal[11].date())},
               'predictions':[{'symbol':'600519.SH','raw_probability':.6,'calibrated_probability':.55}]}
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/'prediction.json';manifest=Path(d)/'manifest.json';out=Path(d)/'review.json'
            write_json(original,batch);write_json(manifest,{'identity':'new'})
            before=digest(original)
            with patch('ashare_quant_lab.direction_inference.initialize',return_value=({},{})), \
                 patch('qlib.data.D') as data:
                data.calendar.return_value=cal
                data.instruments.return_value={}
                data.features.return_value=close
                result=review_direction(original,Path(d),manifest,out)
                with self.assertRaises(FileExistsError):
                    review_direction(original,Path(d),manifest,out)
            self.assertEqual(result['status'],'MATURE_REVIEW')
            self.assertEqual(digest(original),before)
            review=json.loads(out.read_text())
            self.assertEqual(review['prediction_sha256'],before)
            self.assertEqual(review['labels'][0]['y'],1)
            self.assertAlmostEqual(review['labels'][0]['return'],.01)

@unittest.skipUnless(importlib.util.find_spec('qlib'), 'requires official Qlib environment')
class ModelIdentityTests(unittest.TestCase):
    def test_modified_record_and_model_bytes_fail_before_loading_model(self):
        from ashare_quant_lab.direction_data import digest
        from ashare_quant_lab.direction_inference import load_model
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)
            model=directory/'model.txt';model.write_text('original-model-bytes')
            record=directory/'model-record.json'
            write_json(record,{'model_sha256':digest(model),'packages':{'pyqlib':'0.9.7'},'feature_spec':{}})
            trusted=digest(record)
            model.write_text('tampered-model-bytes')
            with self.assertRaisesRegex(StudyError,'model bytes'):
                load_model(directory,trusted)
            record.write_text('{}')
            with self.assertRaisesRegex(StudyError,'explicitly trusted'):
                load_model(directory,trusted)
