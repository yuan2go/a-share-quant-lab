"""Probability metrics with date-equal weighting and whole-date time blocks."""
from __future__ import annotations

from .research_evaluation import StudyError

PROBABILITIES = ('model', 'raw', 'b0', 'b1')


def probability_metrics(rows, column, epsilon=1e-6):
    import numpy as np
    if rows.empty:
        return {'dates': 0, 'pairs': 0, 'log_loss': None, 'brier': None,
                'balanced_accuracy': None, 'confusion_matrix': [[0, 0], [0, 0]], 'calibration_curve': []}
    p, y = rows[column], rows.y
    clipped = p.clip(epsilon, 1 - epsilon)
    loss = -(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))
    predicted = p >= .5
    matrix = [[int(((y == actual) & (predicted == guess)).sum()) for guess in (False, True)] for actual in (0, 1)]
    recalls = [matrix[i][i] / sum(matrix[i]) if sum(matrix[i]) else None for i in (0, 1)]
    weights = 1 / rows.groupby(level='datetime').y.transform('count')
    curve = []
    for i in range(10):
        mask = (p >= i / 10) & ((p < (i + 1) / 10) if i < 9 else (p <= 1))
        if mask.any():
            w = weights[mask]
            curve.append({'lower': i / 10, 'upper': (i + 1) / 10, 'pairs': int(mask.sum()),
                          'date_weight': float(w.sum()), 'mean_probability': float(np.average(p[mask], weights=w)),
                          'observed_up_fraction': float(np.average(y[mask], weights=w))})
    return {'dates': int(rows.index.get_level_values('datetime').nunique()), 'pairs': len(rows),
            'positive_pairs': int(y.sum()), 'not_up_pairs': int((y == 0).sum()),
            'zero_return_pairs': int((rows['return'] == 0).sum()), 'positive_fraction_pairs': float(y.mean()),
            'log_loss': float(loss.groupby(level='datetime').mean().mean()),
            'brier': float(((p - y) ** 2).groupby(level='datetime').mean().mean()),
            'balanced_accuracy': sum(recalls) / 2 if all(r is not None for r in recalls) else None,
            'balanced_accuracy_status': 'DEFINED' if all(r is not None for r in recalls) else 'UNDEFINED_SINGLE_CLASS',
            'confusion_matrix': matrix, 'confusion_axes': 'rows actual 0/1; columns predicted 0/1',
            'calibration_curve': curve}


def block_interval(values, *, block, replicates, seed):
    """Moving blocks on the full ordered date axis, including missing dates."""
    import numpy as np
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    if len(values) < 2 * block or finite.sum() < 2 * block:
        return {'status': 'INSUFFICIENT_DATES', 'lower': None, 'upper': None}
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(replicates):
        starts = rng.integers(0, len(values) - block + 1, size=int(np.ceil(len(values) / block)))
        sample = values[(starts[:, None] + np.arange(block)).ravel()[:len(values)]]
        if np.isfinite(sample).any():
            results.append(float(np.nanmean(sample)))
    return {'status': 'RETROSPECTIVE_MOVING_DATE_BLOCKS', 'block_sessions': block,
            'replicates': replicates, 'seed': seed, 'confidence': .95,
            'lower': float(np.quantile(results, .025)), 'upper': float(np.quantile(results, .975)),
            'axis_dates': len(values), 'observed_dates': int(finite.sum())}


def evaluate(observations, calendar, config):
    import numpy as np
    import pandas as pd
    rows = observations.copy()
    if rows.index.has_duplicates or rows.index.names != ['datetime', 'instrument']:
        raise StudyError('evaluation requires unique canonical date/security keys')
    if not set(rows.y.dropna().unique()) <= {0., 1.}:
        raise StudyError('nonbinary evaluation labels')
    for name in PROBABILITIES:
        finite = rows[name].dropna()
        if not np.isfinite(finite).all() or not finite.between(0, 1).all():
            raise StudyError(f'invalid probability: {name}')
    def summarize(frame):
        common = frame.dropna(subset=['y', 'model', 'b0', 'b1', 'raw'])
        metrics = {name: probability_metrics(common, name, config['epsilon']) for name in PROBABILITIES}
        diffs = {name: metrics['model']['log_loss'] - metrics[name]['log_loss']
                 if len(common) else None for name in ('b0', 'b1')}
        return {'expected_pairs': len(frame), 'mature_label_pairs': int(frame.y.notna().sum()),
                'output_pairs': {name: int(frame[name].notna().sum()) for name in PROBABILITIES},
                'exclusion_reason_counts': frame.reason.value_counts().astype(int).to_dict(),
                'dates': int(common.index.get_level_values('datetime').nunique()), 'pairs': len(common),
                'metrics': metrics, 'model_minus_baseline': diffs,
                'raw_minus_baseline': {name: metrics['raw']['log_loss'] - metrics[name]['log_loss']
                                       if len(common) else None for name in ('b0', 'b1')}}
    summary = summarize(rows)
    common = rows.dropna(subset=['y', *PROBABILITIES])
    daily = pd.DataFrame(index=pd.DatetimeIndex(calendar, name='datetime'))
    for name in PROBABILITIES:
        p = common[name].clip(config['epsilon'], 1 - config['epsilon'])
        loss = -(common.y * np.log(p) + (1 - common.y) * np.log(1 - p))
        daily[name] = loss.groupby(level='datetime').mean()
    intervals = {}
    for name in ('b0', 'b1'):
        daily['model_minus_' + name] = daily.model - daily[name]
        intervals[name] = block_interval(daily['model_minus_' + name], block=config['bootstrap_block'],
                                         replicates=config['bootstrap_replicates'], seed=config['seed'])
    years = sorted(set(rows.index.get_level_values('datetime').year))
    summary['by_year'] = {str(y): summarize(rows.loc[rows.index.get_level_values('datetime').year == y]) for y in years}
    summary['by_security'] = {s: summarize(rows.xs(s, level='instrument', drop_level=False))
                              for s in sorted(set(rows.index.get_level_values('instrument')))}
    summary['own_output_metrics'] = {name: probability_metrics(rows.dropna(subset=['y', name]), name, config['epsilon'])
                                     for name in PROBABILITIES}
    summary['coverage'] = {'expected_pairs': len(rows), 'expected_dates': len(daily),
                            'mature_label_pairs': int(rows.y.notna().sum()),
                            'missing_label_pairs': int(rows.y.isna().sum()),
                            'output_pairs': {k: int(rows[k].notna().sum()) for k in PROBABILITIES},
                            'output_ratio': {k: float(rows[k].notna().mean()) for k in PROBABILITIES},
                            'missing_by_column': rows[['y', *PROBABILITIES]].isna().sum().astype(int).to_dict(),
                            'exclusion_reason_counts': rows.reason.value_counts().astype(int).to_dict(),
                            'zero_return_pairs': int((rows['return'] == 0).sum()),
                            'all_up_dates': int((rows.groupby(level='datetime').y.agg(['min', 'max']).eq(1).all(axis=1)).sum()),
                            'all_not_up_dates': int((rows.groupby(level='datetime').y.agg(['min', 'max']).eq(0).all(axis=1)).sum())}
    summary['uncertainty'] = intervals
    mean_good = all(v is not None and v < 0 for v in summary['model_minus_baseline'].values())
    interval_good = all(x['upper'] is not None and x['upper'] < 0 for x in intervals.values())
    stable = all(all(v is not None and v < 0 for v in year['model_minus_baseline'].values()) for year in summary['by_year'].values())
    summary['research_conclusion'] = ('LIMITED_RETROSPECTIVE_GAIN_NOT_TRADING_QUALIFIED' if mean_good and interval_good and stable
                                       else 'INSUFFICIENT_EVIDENCE' if mean_good else 'NO_INCREMENTAL_GAIN')
    summary['calibration_qualification'] = 'TEMPORALLY_SEPARATE_FIT_ONLY; reliability not certified by Brier or fitted status'
    return summary, daily
