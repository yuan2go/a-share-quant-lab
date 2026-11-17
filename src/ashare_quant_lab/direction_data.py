"""Native Qlib features, calendar-based targets and frozen temporal partitions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .research_evaluation import StudyError, canonical_series

RETURN_EXPRESSION = 'Ref($close,-11)/Ref($close,-1)-1'
MOMENTUM_EXPRESSION = '$close/Ref($close,20)-1'
EVENT = 'adjusted_close(T+11)/adjusted_close(T+1)-1 > 0; zero is not-up'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    """Append-only artifact creation. Never replace a prediction or model record."""
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def direction_labels(returns):
    import numpy as np
    return (returns > 0).astype(float).where(np.isfinite(returns))


# Import Qlib only in the optional research environment, not the core CLI.
def binary_processor():
    from qlib.data.dataset.processor import Processor

    class BinaryLabel(Processor):
        def __call__(self, frame):
            frame = frame.copy()
            frame['label'] = direction_labels(frame['label'])
            return frame
    return BinaryLabel()


def validate_config(path):
    config = json.loads(Path(path).read_text())
    frozen = json.loads((Path(__file__).resolve().parents[2] / 'configs/direction-study.json').read_text())
    if config != frozen:
        raise StudyError('configuration differs from frozen direction protocol; create a new experiment')
    return config


def monthly_split(calendar, anchor, config):
    """All endpoints are SIGNAL dates; embargo uses actual label-end session +11."""
    import pandas as pd
    cal = pd.DatetimeIndex(calendar)
    p = cal.get_loc(pd.Timestamp(anchor))
    end = p - 12  # last calibration label ends no later than P-1
    result = {}
    for name, size in [('calibration', config['calibration_sessions']),
                       ('valid', config['valid_sessions']), ('train', config['train_sessions'])]:
        start = end - size + 1
        if start < 0:
            raise StudyError('insufficient full calendar for frozen rolling windows')
        result[name] = [str(cal[start].date()), str(cal[end].date())]
        end = start - 12
    result['anchor'] = str(cal[p].date())
    result['mature_through'] = str(cal[p - 1].date())
    result['label_end'] = {name: str(cal[cal.get_loc(pd.Timestamp(result[name][1])) + 11].date())
                           for name in ('train', 'valid', 'calibration')}
    return result


def initialize(provider, manifest_path, work_dir):
    import qlib
    from qlib.constant import REG_CN
    from .qlib_dump import verify_binary_identity
    provider, work_dir = Path(provider).resolve(), Path(work_dir).resolve()
    manifest = json.loads(Path(manifest_path).read_text())
    lineage = json.loads((provider / 'aql_source_manifest.json').read_text())
    if (lineage['source_manifest_sha256'] != digest(manifest_path)
            or manifest.get('point_in_time_status') != 'RETROSPECTIVE_ONLY'):
        raise StudyError('snapshot / provider lineage mismatch')
    from .symbols import load_symbols
    cohort = load_symbols(Path(__file__).resolve().parents[2] / 'configs/first-study-cohort.txt')
    if set(manifest['universe']) != set(cohort):
        raise StudyError('direction study requires the original fixed 30-stock cohort')
    verify_binary_identity(provider)
    qlib.init(provider_uri=str(provider), region=REG_CN, kernels=4, joblib_backend='threading',
              local_cache_path=str(work_dir / 'cache'),
              exp_manager={'class': 'MLflowExpManager', 'module_path': 'qlib.workflow.expm',
                           'kwargs': {'uri': str(work_dir / 'mlruns'), 'default_exp_name': 'aql_direction'}})
    return manifest, lineage


def feature_spec():
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.data import ExpressionD
    expressions, names = Alpha158.get_feature_config(None)
    windows = [ExpressionD.get_expression_instance(expr).get_extended_window_size() for expr in expressions]
    if any(right > 0 for _, right in windows) or len(names) != 158:
        raise StudyError('unexpected Alpha158 feature definition or future dependence')
    return {'expressions': expressions, 'names': names, 'windows': [list(w) for w in windows],
            'lookback': max(left for left, _ in windows),
            'infer_processors': [], 'learn_processors': ['BinaryLabel', 'DropnaLabel'],
            'feature_nonfinite_policy': 'native missing values; inf to NaN; no price filling'}


def canonical_frame(frame):
    """Reorder values and keys together, refusing ambiguous or duplicate indices."""
    import pandas as pd
    return pd.concat([canonical_series(frame.iloc[:, i], str(i)) for i in range(frame.shape[1])],
                     axis=1).set_axis(frame.columns, axis=1)


def load_native(manifest, *, with_labels):
    """Use the complete provider calendar, including warmup and missing sessions."""
    import numpy as np
    import pandas as pd
    from qlib.data import D
    from qlib.contrib.data.handler import Alpha158
    cal = pd.DatetimeIndex(D.calendar())
    if list(cal.strftime('%Y-%m-%d')) != manifest['open_dates']:
        raise StudyError('native calendar differs from snapshot')
    codes = sorted(s.split('.')[1] + s.split('.')[0] for s in manifest['universe'])
    available = D.instruments('all')
    if set(str(c).upper() for c in D.list_instruments(available, as_list=True)) != set(codes):
        raise StudyError('native instrument cohort mismatch')
    spec = feature_spec()
    index = pd.MultiIndex.from_product([cal, codes], names=['datetime', 'instrument'])
    fields = ['$open', '$high', '$low', '$close', '$vwap', '$volume']
    bars = canonical_frame(D.features(available, fields, cal[0], cal[-1])).reindex(index)
    valid = np.isfinite(bars).all(axis=1) & (bars > 0).all(axis=1)
    wide = valid.unstack('instrument').reindex(cal)
    eligible = wide.rolling(spec['lookback'] + 1, min_periods=spec['lookback'] + 1).sum().eq(spec['lookback'] + 1)
    quality = eligible.stack().reindex(index).rename('eligible')
    # Official Alpha158 is the feature/label loader; explicitly disable default label normalization.
    if with_labels:
        handler = Alpha158(instruments='all', start_time=cal[0], end_time=cal[-1],
                           infer_processors=[], learn_processors=[],
                           label=([RETURN_EXPRESSION], ['RETURN']))
        raw = canonical_frame(handler.fetch(col_set=['feature', 'label']))
    else:
        from qlib.data.dataset.loader import QlibDataLoader
        loader = QlibDataLoader(config={'feature': (spec['expressions'], spec['names'])})
        raw = canonical_frame(loader.load(instruments='all', start_time=cal[0], end_time=cal[-1]))
    native_keys = raw.index
    raw = raw.reindex(index).replace([np.inf, -np.inf], np.nan)
    close = bars['$close'].unstack('instrument').reindex(cal)
    expected_momentum = close / close.shift(20) - 1
    native_momentum = canonical_series(D.features(available, [MOMENTUM_EXPRESSION], cal[0], cal[-1]).iloc[:, 0], 'momentum').reindex(index)
    expected_momentum = expected_momentum.stack(future_stack=True).reindex(index)
    if not np.allclose(native_momentum, expected_momentum, equal_nan=True, rtol=2e-5, atol=2e-7):
        raise StudyError('native momentum differs from complete calendar shift')
    returns = ((close.shift(-11) / close.shift(-1) - 1).stack(future_stack=True).reindex(index)
               if with_labels else None)
    if with_labels and not np.allclose(raw.loc[native_keys, 'label'].iloc[:, 0], returns.reindex(native_keys), equal_nan=True, rtol=2e-5, atol=2e-7):
        raise StudyError('native returns differ from complete calendar shift')
    audit = {'feature_count': len(spec['names']), 'lookback_sessions': spec['lookback'],
             'calendar_sessions': len(cal), 'expected_pairs': len(index), 'eligible_pairs': int(quality.sum()),
             'current_bar_missing_pairs': int((~valid).sum()),
             'incomplete_lookback_pairs': int((~quality & valid).sum()),
             'nonfinite_feature_values': int(raw['feature'].isna().sum().sum()),
             'momentum_audit': 'MATCH_COMPLETE_CALENDAR_SHIFT',
             'label_audit_native_pairs': len(native_keys) if with_labels else 0,
             'label_audit': 'MATCH_COMPLETE_CALENDAR_SHIFT' if with_labels else 'NOT_LOADED'}
    return cal, raw, quality, native_momentum, returns, spec, audit


def dataset_from_frame(frame, segments, *, learn):
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    handler = DataHandlerLP(data_loader={'class': 'StaticDataLoader', 'module_path': 'qlib.data.dataset.loader',
                                        'kwargs': {'config': frame}}, infer_processors=[],
                            learn_processors=[binary_processor(), {'class': 'DropnaLabel'}] if learn else [])
    return DatasetH(handler=handler, segments=segments)
