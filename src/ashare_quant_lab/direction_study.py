"""Frozen monthly native Qlib binary study. No selection using evaluation results."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .direction_data import (dataset_from_frame, digest, direction_labels, initialize,
                             load_native, monthly_split, validate_config, write_json)
from .research_evaluation import StudyError, canonical_series

MODEL_PARAMETERS = dict(loss='binary', learning_rate=.05, max_depth=6, num_leaves=31,
                        num_threads=4, num_boost_round=240, early_stopping_rounds=30,
                        seed=23, deterministic=True, force_col_wise=True)


def logistic_fit(x, y, *, standardize):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    x = np.asarray(x, dtype=float).reshape(-1, 1)
    if len(x) < 100 or len(set(y)) != 2:
        raise StudyError('logistic fitting requires >=100 rows and both classes')
    scaler = StandardScaler().fit(x) if standardize else None
    transformed = scaler.transform(x) if scaler is not None else x
    model = LogisticRegression(C=1., solver='lbfgs', max_iter=1000, random_state=23).fit(transformed, y)
    if model.n_iter_[0] >= 1000:
        raise StudyError('logistic model did not converge')
    return {'coefficient': float(model.coef_[0, 0]), 'intercept': float(model.intercept_[0]),
            'mean': float(scaler.mean_[0]) if scaler is not None else 0.,
            'scale': float(scaler.scale_[0]) if scaler is not None else 1.,
            'fit_rows': len(x), 'iterations': int(model.n_iter_[0])}


def logistic_predict(fit, values):
    import numpy as np
    from scipy.special import expit
    return expit((values - fit['mean']) / fit['scale'] * fit['coefficient'] + fit['intercept'])


def logit(probability):
    import numpy as np
    p = probability.clip(1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def native_model_fit(dataset, rounds=None):
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.workflow import R
    model = LGBModel(**MODEL_PARAMETERS)
    with R.start(experiment_name='aql_direction_binary'):
        model.fit(dataset, num_boost_round=rounds, early_stopping_rounds=0 if rounds else None, verbose_eval=False)
    return model


def train_month(raw, eligible, momentum, calendar, anchor, config, directory, identity, spec, *, repeat=False):
    import numpy as np
    import pandas as pd
    from qlib.data.dataset.handler import DataHandlerLP
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    split = monthly_split(calendar, anchor, config)
    # Keep only backward-looking data-quality-qualified rows. Label drop is learn-only.
    frame = raw.loc[eligible].loc[pd.Timestamp(split['train'][0]):pd.Timestamp(split['calibration'][1])]
    segments = {name: tuple(split[name]) for name in ('train', 'valid', 'calibration')}
    dataset = dataset_from_frame(frame, segments, learn=True)
    train = dataset.prepare('train', col_set='label', data_key=DataHandlerLP.DK_L).iloc[:, 0]
    valid = dataset.prepare('valid', col_set='label', data_key=DataHandlerLP.DK_L).iloc[:, 0]
    for labels in (train, valid):
        if set(labels.unique()) != {0., 1.} or not np.isfinite(labels).all():
            raise StudyError('native learning labels must be finite binary 0/1 with both classes')
    expected_start = calendar.get_loc(pd.Timestamp(split['train'][0]))
    if expected_start < spec['lookback']:
        raise StudyError('training window starts before full Alpha158 warmup')
    model = native_model_fit(dataset)
    best_iteration = model.model.best_iteration
    final_dataset = dataset
    rounds = None
    if config.get('refit'):
        end = calendar.get_loc(pd.Timestamp(split['valid'][1]))
        start = end - config['train_sessions'] + 1
        split['refit'] = [str(calendar[start].date()), str(calendar[end].date())]
        split['label_end']['refit'] = str(calendar[end + 11].date())
        if split['label_end']['refit'] >= split['calibration'][0] or best_iteration < 1:
            raise StudyError('invalid refit/calibration boundary or selected iteration')
        final_dataset = dataset_from_frame(frame, {'train': tuple(split['refit'])}, learn=True)
        rounds = best_iteration
        model = native_model_fit(final_dataset, rounds)
    model.model.save_model(str(directory / 'model.txt'))
    train = canonical_series(train, 'y')
    train_momentum = momentum.reindex(train.index)
    mask = train_momentum.notna()
    baseline = logistic_fit(train_momentum[mask], train[mask], standardize=True)
    b0 = float((train.sum() + 1) / (len(train) + 2))
    cal_p = canonical_series(model.predict(dataset, segment='calibration'), 'raw')
    cal_y = canonical_series(dataset.prepare('calibration', col_set='label', data_key=DataHandlerLP.DK_L).iloc[:, 0], 'y')
    calibration = pd.concat([cal_p, cal_y], axis=1).dropna()
    calibrator, status = None, 'UNAVAILABLE_INSUFFICIENT_OR_SINGLE_CLASS'
    if len(calibration) >= 100 and calibration.y.nunique() == 2:
        calibrator = logistic_fit(logit(calibration.raw), calibration.y, standardize=False)
        status = 'TEMPORAL_PLATT_FITTED_NOT_RELIABILITY_CERTIFIED'
    record = {**identity, 'schema_version': 1, 'split': split, 'parameters': MODEL_PARAMETERS,
              'feature_spec': spec, 'calibrator': calibrator, 'calibration_status': status,
              'baseline_recent': float((cal_y.sum() + 1) / (len(cal_y) + 2)),
              'baseline_b0': b0, 'baseline_b1': baseline, 'train_pairs': len(train), 'valid_pairs': len(valid),
              'calibration_pairs': len(calibration), 'train_positive_fraction': float(train.mean()),
              'best_iteration': best_iteration, 'model_sha256': digest(directory / 'model.txt'),
              'created_at': datetime.now(timezone.utc).isoformat(), 'native_repeat': 'NOT_REQUESTED'}
    if repeat:
        second = native_model_fit(final_dataset, rounds)
        second.model.save_model(str(directory / 'repeat-model.txt'))
        other = canonical_series(second.predict(dataset, 'calibration'), 'raw')
        if digest(directory / 'repeat-model.txt') != record['model_sha256'] or not other.equals(cal_p):
            raise StudyError('same-input native training not reproducible')
        record['native_repeat'] = 'IDENTICAL_MODEL_BYTES_AND_CALIBRATION_PROBABILITIES'
    write_json(directory / 'model-record.json', record)
    return model, record


def predict_frame(model, record, features, momentum):
    import numpy as np
    import pandas as pd
    dataset = dataset_from_frame(features, {'test': (features.index.get_level_values('datetime').min(),
                                                   features.index.get_level_values('datetime').max())}, learn=False)
    probability = canonical_series(model.predict(dataset), 'raw')
    output = pd.DataFrame({'raw': probability})
    output['model'] = logistic_predict(record['calibrator'], logit(probability)) if record['calibrator'] else np.nan
    output['recent'] = record.get('baseline_recent', np.nan)
    output['b0'] = record['baseline_b0']
    output['b1'] = logistic_predict(record['baseline_b1'], momentum.reindex(output.index))
    return output


def code_identity():
    base = Path(__file__).resolve().parents[2]
    return {'git_revision': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=base, capture_output=True,
                                            text=True, check=True).stdout.strip(),
            'source_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')},
            'python': platform.python_version(),
            'packages': {p: importlib.metadata.version(p) for p in
                         ('pyqlib', 'lightgbm', 'pandas', 'numpy', 'scikit-learn', 'duckdb', 'pyarrow', 'mlflow')}}


def run_direction_study(provider, manifest_path, config_path, output):
    import numpy as np
    import pandas as pd
    from .direction_evaluation import evaluate
    config = validate_config(config_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    state = {'work_package': config['work_package'], 'status': 'RUNNING', 'months_completed': []}
    def save_state():
        # Progress is mutable; original predictions/models/reports are exclusive-create.
        (output / 'progress.json').write_text(json.dumps(state, indent=2) + '\n')
    save_state()
    try:
        manifest, lineage = initialize(provider, manifest_path, output)
        cal, raw, eligible, momentum, returns, spec, audit = load_native(manifest, with_labels=True)
        identity = {**code_identity(), 'work_package': config['work_package'],
                    'snapshot_id': digest(manifest_path), 'config_sha256': digest(config_path),
                    'binary_lineage_sha256': digest(Path(provider) / 'aql_source_manifest.json')}
        write_json(output / 'native-audit.json', audit)
        eval_dates = cal[(cal >= config['evaluation'][0]) & (cal <= config['evaluation'][1])]
        if not len(eval_dates) or eval_dates[-1] != pd.Timestamp(config['evaluation'][1]):
            raise StudyError('evaluation endpoint missing from provider calendar')
        if cal.get_loc(eval_dates[-1]) + 11 >= len(cal):
            raise StudyError('evaluation labels have not matured')
        target = raw.loc[eval_dates[0]:eval_dates[-1]].index
        observations = pd.DataFrame(index=target, columns=['raw', 'model', 'b0', 'b1'], dtype=float)
        observations['return'] = returns.reindex(target)
        observations['y'] = direction_labels(observations['return'])
        observations['reason'] = np.where(eligible.reindex(target), 'ELIGIBLE', 'INCOMPLETE_RAW_LOOKBACK')
        observations['model_id'] = ''
        periods = eval_dates.to_period('M').unique()
        for number, period in enumerate(periods):
            dates = eval_dates[eval_dates.to_period('M') == period]
            anchor = cal[cal.to_period('M') == period][0]
            model, record = train_month(raw, eligible, momentum, cal, anchor, config,
                                         output / 'models' / str(period), identity, spec, repeat=number == 0)
            keys = target[(target.get_level_values('datetime') >= dates[0]) & (target.get_level_values('datetime') <= dates[-1])]
            allowed = keys[eligible.reindex(keys).to_numpy()]
            predicted = predict_frame(model, record, raw.loc[allowed, ['feature']], momentum)
            observations.loc[keys, 'model_id'] = record['model_sha256']
            for name in (('raw', 'model', 'b0', 'b1', 'recent') if config.get('refit') else ('raw', 'model', 'b0', 'b1')):
                observations.loc[predicted.index, name] = predicted[name]
            if record['calibrator'] is None:
                observations.loc[allowed, 'reason'] = 'CALIBRATION_UNAVAILABLE'
            state['months_completed'].append(str(period))
            save_state()
            print(json.dumps({'month_complete': str(period), 'best_iteration': record['best_iteration']}), flush=True)
        observations.to_parquet(output / 'observations.parquet')
        summary, daily = evaluate(observations, eval_dates, config)
        if config.get('refit'):
            summary['research_conclusion'] = 'AWAITING_FROZEN_FOUR_COMPARATOR_ANALYSIS'
        daily.to_parquet(output / 'daily-loss.parquet')
        # Fit the latest month with the identical frozen schedule, independent of historical results.
        latest_period = cal[-1].to_period('M')
        latest_dir = output / 'models' / str(latest_period)
        if not latest_dir.exists():
            train_month(raw, eligible, momentum, cal, cal[cal.to_period('M') == latest_period][0], config,
                        latest_dir, identity, spec)
        report = {**identity, 'status': 'RETROSPECTIVE_COMPLETE_NOT_PIT_OR_TRADING',
                  'data_kind': manifest.get('data_kind', 'REAL_SOURCE_RETROSPECTIVE'), 'native_audit': audit,
                  'evaluation': summary, 'latest_model_directory': str(latest_dir),
                  'observations_sha256': digest(output / 'observations.parquet'),
                  'daily_loss_sha256': digest(output / 'daily-loss.parquet'),
                  'created_at': datetime.now(timezone.utc).isoformat()}
        write_json(output / 'study-report.json', report)
        state['status'] = report['status']
        save_state()
        return {'status': report['status'], 'report': str(output / 'study-report.json'),
                'research_conclusion': summary['research_conclusion'], 'latest_model_directory': str(latest_dir)}
    except Exception as exc:
        state.update(status='FAILED', failure_class=type(exc).__name__)
        save_state()
        raise


def train_latest(provider, manifest_path, config_path, output):
    """Same frozen monthly schedule; no reading evaluation results or parameter selection."""
    config = validate_config(config_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest, _ = initialize(provider, manifest_path, output)
    cal, raw, eligible, momentum, _, spec, audit = load_native(manifest, with_labels=True)
    identity = {**code_identity(), 'work_package': config['work_package'],
                'snapshot_id': digest(manifest_path), 'config_sha256': digest(config_path),
                'binary_lineage_sha256': digest(Path(provider) / 'aql_source_manifest.json')}
    anchor = cal[cal.to_period('M') == cal[-1].to_period('M')][0]
    _, record = train_month(raw, eligible, momentum, cal, anchor, config, output / 'model', identity, spec)
    write_json(output / 'native-audit.json', audit)
    return {'model_dir': str(output / 'model'), 'model_record_sha256': digest(output / 'model/model-record.json'),
            'model_id': record['model_sha256']}
