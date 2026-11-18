"""Explicit SYNTHETIC native integration; never a real-market research result.

Run with the Qlib environment, --root on external storage and the official
v0.9.7 checkout. Uses the frozen cohort, dates, model and normal ingestion.
"""
import argparse
import json
import hashlib
import math
from datetime import date, timedelta
from pathlib import Path

from ashare_quant_lab.market_ingest import ingest_market
from ashare_quant_lab.market_export import export_market_parquet
from ashare_quant_lab.qlib_dump import dump_parquet_using_official_qlib
from ashare_quant_lab.first_study import run_first_qlib_study
from ashare_quant_lab.symbols import load_symbols


class SyntheticSource:
    def query(self, api_name, **params):
        import numpy as np
        start = date(2019, 1, 2)
        days = [start + timedelta(days=i) for i in range((date(2026, 10, 30) - start).days + 1)]
        if api_name == 'trade_cal':
            return [{'exchange': 'SSE', 'cal_date': str(d), 'is_open': int(d.weekday() < 5)} for d in days]
        days = [d for d in days if d.weekday() < 5]
        symbol = params['ts_code']
        seed = int(symbol[:6])
        rng = np.random.default_rng(seed)
        shocks = rng.normal(.0001, .012, len(days))
        adjusted = (20 + seed % 80) * np.exp(np.cumsum(shocks))
        records = []
        for i, (d, close) in enumerate(zip(days, adjusted)):
            factor = 1 + (i // 650) * .1
            close /= factor
            volume = 10000 + (seed % 1000) + 500 * (1 + math.sin(i / 5))
            if api_name == 'adj_factor':
                row = {'ts_code': symbol, 'trade_date': str(d), 'adj_factor': factor}
            else:
                row = {'ts_code': symbol, 'trade_date': str(d), 'open': close * .998,
                       'high': close * 1.012, 'low': close * .988, 'close': close,
                       'vol': volume, 'amount': volume * close / 10}
            records.append(row)
        return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--qlib-repo', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    symbols = load_symbols(repo / 'configs/first-study-cohort.txt')
    capture = ingest_market(root / 'synthetic.duckdb', SyntheticSource(), symbols,
                            date(2019, 1, 2), date(2026, 10, 30))
    export = export_market_parquet(root / 'synthetic.duckdb', symbols, date(2019, 1, 2),
                                   date(2026, 10, 30), root / 'parquet')
    manifest_path = root / 'parquet/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(data_kind='SYNTHETIC_ENGINEERING_ONLY', source='Deterministic synthetic test generator; no market API')
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    export['data_snapshot_id'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    conversion = dump_parquet_using_official_qlib(args.qlib_repo, root / 'parquet', root / 'binary')
    study = run_first_qlib_study(root / 'binary', root / 'parquet/manifest.json',
                                repo / 'configs/first-study.json', root / 'study')
    from ashare_quant_lab.direction_study import run_direction_study, predict_frame
    from ashare_quant_lab.direction_data import digest, load_native
    from ashare_quant_lab.direction_inference import load_model
    direction = run_direction_study(root / 'binary', manifest_path,
                                    repo / 'configs/direction-study.json', root / 'direction')
    model_dir = Path(direction['latest_model_directory'])
    model, record = load_model(model_dir, digest(model_dir / 'model-record.json'))
    cal, features, eligible, momentum, targets, _, audit = load_native(manifest, with_labels=False)
    assert targets is None and 'label' not in features.columns.get_level_values(0)
    keys = features.index[(features.index.get_level_values('datetime') == cal[-1]) & eligible.to_numpy()]
    predicted = predict_frame(model, record, features.loc[keys, ['feature']], momentum)
    assert len(predicted) == 30 and predicted['model'].notna().all()
    assert predicted.equals(predict_frame(model, record, features.loc[keys, ['feature']], momentum))
    direction['label_free_native_inference'] = {'pairs': len(predicted), 'label_audit': audit['label_audit'],
                                               'repeat': 'IDENTICAL', 'data_kind': 'SYNTHETIC_ENGINEERING_ONLY'}
    report = {'data_kind': 'SYNTHETIC_ENGINEERING_ONLY', 'real_research_accepted': False,
              'capture': capture, 'export': export, 'conversion': conversion, 'study': study, 'direction': direction}
    (root / 'engineering-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'data_kind': report['data_kind'], 'status': 'PASS', 'root': str(root)}))


if __name__ == '__main__':
    main()
