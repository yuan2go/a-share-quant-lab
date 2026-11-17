"""Label-free latest inference and append-only maturity review of retained forecasts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .direction_data import (EVENT, digest, initialize, load_native, write_json)
from .direction_study import code_identity, predict_frame
from .research_evaluation import StudyError


def expected_session(clock, now):
    """18:00 is an operational gate, not proof of historical publication timing."""
    import pandas as pd
    local = now.astimezone(ZoneInfo('Asia/Shanghai'))
    fetched = datetime.fromisoformat(clock['captured_at'])
    if fetched.tzinfo is None:
        raise StudyError('source clock timestamp must include timezone')
    if now - fetched > timedelta(days=1) or fetched > now + timedelta(minutes=5):
        raise StudyError('source calendar clock expired or in the future; refresh clock')
    if clock.get('exchanges') != 'SSE_SZSE_MATCH':
        raise StudyError('latest inference needs source calendar agreement')
    dates = pd.DatetimeIndex(clock['open_dates'])
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise StudyError('invalid source clock calendar')
    if clock['range_end'] < local.date().isoformat() or clock['range_start'] > (local.date() - timedelta(days=20)).isoformat():
        raise StudyError('source clock must span recent sessions through today')
    bound = local.date() if local.hour >= 18 else local.date() - timedelta(days=1)
    completed = dates[dates <= pd.Timestamp(bound)]
    if not len(completed):
        raise StudyError('no completed source session in clock')
    return completed[-1], dates


def load_model(directory, expected_record_sha256):
    import lightgbm as lgb
    import qlib
    from qlib.contrib.model.gbdt import LGBModel
    from .direction_data import feature_spec
    directory = Path(directory)
    record_path = directory / 'model-record.json'
    if digest(record_path) != expected_record_sha256:
        raise StudyError('model record differs from explicitly trusted SHA256')
    record = json.loads(record_path.read_text())
    if (digest(directory / 'model.txt') != record['model_sha256']
            or record['packages']['pyqlib'] != qlib.__version__
            or record['feature_spec'] != feature_spec()):
        raise StudyError('model bytes, native version or feature/processor specification mismatch')
    model = LGBModel(**record['parameters'])
    model.model = lgb.Booster(model_file=str(directory / 'model.txt'))
    if model.model.num_feature() != 158 or model.model.params.get('objective') != 'binary':
        raise StudyError('trusted model is not a 158-feature binary model')
    return model, record


def infer_direction(provider, manifest_path, model_directory, record_sha256, clock_path, output):
    import numpy as np
    import pandas as pd
    from .symbols import qlib_to_symbol
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('immutable prediction path already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest, _ = initialize(provider, manifest_path, output.parent / ('inference-cache-' + output.stem))
    model, record = load_model(model_directory, record_sha256)
    cal, raw, eligible, momentum, _, spec, audit = load_native(manifest, with_labels=False)
    now = datetime.now(timezone.utc)
    clock = json.loads(Path(clock_path).read_text())
    expected, future = expected_session(clock, now)
    signal = cal[-1]
    quality_latest = eligible.loc[signal]
    status = 'CURRENT_COMPLETED_SESSION_RESEARCH_ONLY'
    if signal != expected:
        status = 'STALE_DATA' if signal < expected else 'BLOCKED_UNCOMPLETED_SESSION'
    elif signal.to_period('M') != pd.Timestamp(record['split']['anchor']).to_period('M'):
        status = 'STALE_MODEL'
    elif not quality_latest.all():
        status = 'INCOMPLETE_COHORT_DATA'
    if pd.Timestamp(record['split']['mature_through']) >= signal:
        raise StudyError('model training information is not prior to prediction signal')
    allowed = raw.index[(raw.index.get_level_values('datetime') == signal) & eligible.to_numpy()]
    if len(allowed):
        prediction = predict_frame(model, record, raw.loc[allowed, ['feature']], momentum)
        repeated = predict_frame(model, record, raw.loc[allowed, ['feature']], momentum)
        if not prediction.equals(repeated):
            raise StudyError('repeat label-free predictions differ')
    else:
        prediction = pd.DataFrame(columns=['raw', 'model', 'b0', 'b1'])
    future_dates = future[future > signal]
    interval = {'start_session': 'T+1 close', 'end_session': 'T+11 close', 'holding_periods': 10,
                'start_date': str(future_dates[0].date()) if len(future_dates) >= 1 else None,
                'end_date': str(future_dates[10].date()) if len(future_dates) >= 11 else None}
    payload = {'schema_version': 1, 'work_package': record['work_package'], 'kind': 'DIRECTION_PREDICTION',
               'inference_code': code_identity(), 'status': status, 'data_kind': manifest.get('data_kind', 'REAL_SOURCE_RETROSPECTIVE'),
               'generated_at': now.isoformat(), 'data_through': str(signal.date()),
               'expected_latest_completed_session': str(expected.date()), 'prediction_interval': interval,
               'up_event': EVENT, 'model_id': record['model_sha256'], 'model_record_sha256': record_sha256,
               'training_snapshot_id': record['snapshot_id'], 'inference_snapshot_id': digest(manifest_path),
               'snapshot_exported_at': manifest['capture_timestamp'],
               'source_capture_ids': manifest['source_capture_ids'], 'source_clock_sha256': digest(clock_path),
               'training_split': record['split'], 'calibration_status': record['calibration_status'],
               'adoption_status': 'RESEARCH_ONLY_NOT_TRADING_QUALIFIED',
               'judgment_status': 'NO_RELIABLE_JUDGMENT_ESTABLISHED; not a flat/oscillating forecast',
               'native_audit': audit, 'repeat_inference': 'IDENTICAL_NO_FIT_NO_LABELS', 'predictions': []}
    for code, good in quality_latest.items():
        key = (signal, code)
        values = prediction.loc[key] if key in prediction.index else None
        def value(name):
            return float(values[name]) if values is not None and np.isfinite(values[name]) else None
        payload['predictions'].append({'symbol': qlib_to_symbol(code), 'raw_probability': value('raw'),
                                       'calibrated_probability': value('model'), 'b0_probability': value('b0'),
                                       'b1_probability': value('b1'),
                                       'data_quality': 'FULL_RAW_LOOKBACK' if good else 'INCOMPLETE_RAW_LOOKBACK'})
    write_json(output, payload)
    return {'status': status, 'prediction_path': str(output), 'prediction_sha256': digest(output),
            'data_through': payload['data_through'], 'outputs': len(prediction)}


def review_direction(prediction_path, provider, manifest_path, output):
    import numpy as np
    import pandas as pd
    from qlib.data import D
    from .research_evaluation import canonical_series
    batch = json.loads(Path(prediction_path).read_text())
    if batch.get('kind') != 'DIRECTION_PREDICTION' or batch.get('up_event') != EVENT:
        raise StudyError('unsupported prediction record')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('review exists; choose a new append-only review path')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest, _ = initialize(provider, manifest_path, output.parent / ('review-cache-' + output.stem))
    cal = pd.DatetimeIndex(D.calendar())
    signal = pd.Timestamp(batch['data_through'])
    if signal not in cal:
        raise StudyError('original signal session absent from review calendar')
    pos = cal.get_loc(signal)
    result = {'kind': 'DIRECTION_MATURITY_REVIEW', 'prediction_sha256': digest(prediction_path),
              'review_code': code_identity(), 'model_id': batch['model_id'], 'original_inference_snapshot_id': batch['inference_snapshot_id'],
              'review_snapshot_id': digest(manifest_path), 'reviewed_at': datetime.now(timezone.utc).isoformat(),
              'data_through': str(cal[-1].date()), 'labels': [],
              'revision_qualification': 'new capture may revise adjusted history; original forecast is preserved'}
    if pos + 11 < len(cal):
        entry, exit_ = cal[pos + 1], cal[pos + 11]
        if (batch['prediction_interval']['start_date'] not in (None, str(entry.date()))
                or batch['prediction_interval']['end_date'] not in (None, str(exit_.date()))):
            raise StudyError('review calendar interval differs from original forecast')
        close = canonical_series(D.features(D.instruments('all'), ['$close'], entry, exit_).iloc[:, 0], 'close')
        for prediction in batch['predictions']:
            symbol = prediction['symbol']
            code = symbol.split('.')[1] + symbol.split('.')[0]
            a, b = close.get((entry, code), np.nan), close.get((exit_, code), np.nan)
            realized = float(b / a - 1) if np.isfinite(a) and np.isfinite(b) and a > 0 else None
            result['labels'].append({'symbol': symbol, 'return': realized,
                                      'y': int(realized > 0) if realized is not None else None,
                                      'zero_return': realized == 0 if realized is not None else None,
                                      'status': 'MATURE' if realized is not None else 'MISSING_ENDPOINT_PRICE',
                                      'original_raw_probability': prediction['raw_probability'],
                                      'original_calibrated_probability': prediction['calibrated_probability']})
        for row in result['labels']:
            if row['y'] is None:
                continue
            row['probability_review'] = {}
            for name in ('raw', 'calibrated'):
                p = row['original_' + name + '_probability']
                if p is not None:
                    clipped = min(1 - 1e-6, max(1e-6, p))
                    row['probability_review'][name] = {
                        'log_loss': float(-row['y'] * np.log(clipped) - (1 - row['y']) * np.log(1 - clipped)),
                        'brier': (p - row['y']) ** 2,
                        'correct_at_fixed_half': int(p >= .5) == row['y']}
        result['status'] = 'MATURE_REVIEW' if all(x['y'] is not None for x in result['labels']) else 'PARTIAL_MISSING_LABELS'
    else:
        result['status'] = 'PENDING_FUTURE_LABELS'
        result['labels'] = [{'symbol': p['symbol'], 'y': None, 'status': 'PENDING_FUTURE_LABELS'} for p in batch['predictions']]
    write_json(output, result)
    return {'status': result['status'], 'review_path': str(output), 'review_sha256': digest(output)}
