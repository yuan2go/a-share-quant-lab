"""Named-key alignment and a single shared denominator for the frozen study."""
from __future__ import annotations


class StudyError(RuntimeError):
    pass


def canonical_series(series, name):
    import numpy as np
    import pandas as pd

    if not isinstance(series, pd.Series) or not isinstance(series.index, pd.MultiIndex):
        raise StudyError(f'{name}: expected a Series with a named MultiIndex')
    if series.index.nlevels != 2 or set(series.index.names) != {'datetime', 'instrument'}:
        raise StudyError(f'{name}: expected datetime/instrument index levels')
    result = series.reorder_levels(['datetime', 'instrument']).copy()
    dates = pd.to_datetime(result.index.get_level_values('datetime'))
    if dates.tz is not None or not dates.equals(dates.normalize()):
        raise StudyError(f'{name}: expected timezone-naive daily timestamps')
    instruments = result.index.get_level_values('instrument').astype(str).str.upper()
    result.index = pd.MultiIndex.from_arrays([dates, instruments], names=['datetime', 'instrument'])
    if result.index.has_duplicates:
        raise StudyError(f'{name}: duplicate date/security observations')
    result = pd.to_numeric(result, errors='raise').astype(float)
    return result.where(np.isfinite(result)).sort_index().rename(name)


def paired_rank_ic(prediction, momentum, label, min_count, *, min_days=20):
    import pandas as pd

    series = [canonical_series(s, n) for s, n in
              [(prediction, 'model'), (momentum, 'momentum'), (label, 'label')]]
    union = pd.concat(series, axis=1)
    common = union.dropna()
    daily, excluded = [], []
    for day, rows in common.groupby(level='datetime'):
        reason = None
        if len(rows) < min_count:
            reason = 'below_min_cross_section'
        elif any(rows[k].nunique() < 2 for k in ('model', 'momentum', 'label')):
            reason = 'constant_score_or_label'
        if reason:
            excluded.append({'date': str(day.date()), 'pairs': len(rows), 'reason': reason})
            continue
        ml = float(rows.model.corr(rows.label, method='spearman'))
        baseline = float(rows.momentum.corr(rows.label, method='spearman'))
        daily.append({'date': str(day.date()), 'pairs': len(rows),
                      'model_rank_ic': ml, 'momentum_rank_ic': baseline,
                      'difference': ml - baseline})
    if len(daily) < min_days:
        raise StudyError(f'insufficient paired IC evaluation days: {len(daily)} < {min_days}')

    def summarize(records):
        n = len(records)
        ml = sum(r['model_rank_ic'] for r in records) / n
        baseline = sum(r['momentum_rank_ic'] for r in records) / n
        return {'days': n, 'pairs': sum(r['pairs'] for r in records),
                'model_mean_rank_ic': ml, 'momentum_mean_rank_ic': baseline,
                'difference': ml - baseline}

    summary = summarize(daily)
    summary.update({
        'min_cross_section': min_count,
        'input_finite_pairs': {s.name: int(s.notna().sum()) for s in series},
        'union_pairs': len(union), 'common_finite_pairs': len(common),
        'excluded_nonfinite_or_missing_pairs': len(union) - len(common),
        'missing_or_nonfinite_by_column': union.isna().sum().astype(int).to_dict(),
        'excluded_days': excluded,
        'days_without_any_common_pairs': sorted(set(str(d.date()) for d in union.index.get_level_values('datetime'))
                                              - set(str(d.date()) for d in common.index.get_level_values('datetime'))),
        'by_year': {y: summarize([r for r in daily if r['date'][:4] == y])
                    for y in sorted({r['date'][:4] for r in daily})},
        'statistical_significance': 'NOT_ESTABLISHED_OVERLAPPING_10_SESSION_TARGETS',
    })
    return summary, daily, union
