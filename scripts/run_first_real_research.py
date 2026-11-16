"""Run the frozen REAL study; persist failures without publishing raw data.

Supply TUSHARE_TOKEN in the environment, never on the command line. Each run
uses a new directory on the explicitly selected external data volume.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--qlib-repo', type=Path, required=True)
    args = parser.parse_args()
    root = args.data_root.expanduser().resolve()
    if not str(root).startswith('/Volumes/'):
        parser.error('this work package requires an external /Volumes/ data root')
    root.mkdir(parents=True, exist_ok=True)
    temp = root / 'tmp'
    temp.mkdir(exist_ok=True)
    os.environ['TMPDIR'] = str(temp)
    tempfile.tempdir = str(temp)
    os.environ['MPLCONFIGDIR'] = str(root / 'cache/matplotlib')
    run = root / 'runs' / ('real-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'src'))
    from ashare_quant_lab.capture_audit import RecordingSource, audit_recorded_capture
    from ashare_quant_lab.source_audit import audit_source
    from ashare_quant_lab.tushare_source import TushareClient, SourceError
    from ashare_quant_lab.market_ingest import ingest_market
    from ashare_quant_lab.market_store import connect_store
    from ashare_quant_lab.market_export import export_market_parquet
    from ashare_quant_lab.qlib_dump import dump_parquet_using_official_qlib
    from ashare_quant_lab.first_study import run_first_qlib_study
    from ashare_quant_lab.symbols import load_symbols

    report = {'work_package': 'WP-AQL-FIRST-REAL-RESEARCH-01', 'data_kind': 'REAL',
              'created_at': datetime.now(timezone.utc).isoformat(), 'run_directory': str(run),
              'status': 'RUNNING', 'phases': {}, 'real_research_accepted': False,
              'metrics': None, 'economic_net_return': None, 'buy_sell_development': 'DO_NOT_ADVANCE'}

    def save():
        (run / 'execution.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    phase = 'source_preflight'
    save()
    try:
        audit = audit_source(date(2026, 9, 1), date(2026, 9, 30))
        report['phases'][phase] = audit
        save()
        if audit['status'] != 'RECEIVED_AND_DIMENSIONALLY_VALIDATED_NOT_PIT':
            report['status'] = audit['status']
            return 2
        source = TushareClient()
        db = run / 'market.duckdb'
        phase = 'overlap_revision_check'
        ids = [ingest_market(db, source, ['600519.SH'], date(2026, 9, 1), date(2026, 9, 30), pace_seconds=2)['capture_id']
               for _ in range(2)]
        with connect_store(db, read_only=True) as conn:
            changed = conn.execute("""WITH a AS (SELECT * FROM daily_bars WHERE capture_id=?),
                b AS (SELECT * FROM daily_bars WHERE capture_id=?)
                SELECT COUNT(*) FROM a FULL OUTER JOIN b USING(symbol,trade_date)
                WHERE a.capture_id IS NULL OR b.capture_id IS NULL OR
                  a.cumulative_factor<>b.cumulative_factor OR a.close<>b.close OR
                  a.open<>b.open OR a.high<>b.high OR a.low<>b.low OR
                  a.volume_shares<>b.volume_shares OR a.amount_cny<>b.amount_cny""", ids).fetchone()[0]
        report['phases'][phase] = {'capture_ids': ids, 'changed_or_missing_rows': changed,
                                   'qualification': 'same-run repeat only, not historical revision proof'}
        if changed:
            raise SourceError('source changed across repeated short-window capture')
        save()
        phase = 'frozen_capture'
        recording = RecordingSource(source, run / 'source-responses')
        report['phases'][phase] = ingest_market(db, recording, load_symbols(repo / 'configs/first-study-cohort.txt'),
                                                date(2019, 1, 2), date(2026, 10, 30), pace_seconds=2)
        save()
        phase = 'capture_quality'
        recording.query('trade_cal', exchange='SZSE', start_date='20190102', end_date='20261030')
        quality = audit_recorded_capture(db, report['phases']['frozen_capture']['capture_id'], recording)
        (run / 'capture-quality.json').write_text(json.dumps(quality, indent=2) + '\n')
        report['phases'][phase] = quality
        save()
        if quality['outlier_count']:
            raise SourceError('capture source consistency outliers require review before training')
        phase = 'parquet'
        report['phases'][phase] = export_market_parquet(db, load_symbols(repo / 'configs/first-study-cohort.txt'),
                                                        date(2019, 1, 2), date(2026, 10, 30), run / 'parquet')
        save()
        phase = 'official_binary'
        report['phases'][phase] = dump_parquet_using_official_qlib(args.qlib_repo, run / 'parquet', run / 'binary')
        save()
        phase = 'native_study'
        report['phases'][phase] = run_first_qlib_study(run / 'binary', run / 'parquet/manifest.json',
                                                     repo / 'configs/first-study.json', run / 'study')
        study = json.loads((run / 'study/study-report.json').read_text())
        report['metrics'] = study['paired_evaluation']
        report['status'] = 'RETROSPECTIVE_RUN_COMPLETE_NOT_PIT_OR_TRADING_QUALIFIED'
        report['real_research_accepted'] = True
        return 0
    except Exception as exc:
        report['status'] = 'FAILED'
        # Native diagnostic stack belongs only in private external run logs.
        import traceback
        (run / 'failure.txt').write_text(traceback.format_exc())
        report['failure'] = {'phase': phase, 'class': type(exc).__name__}
        report['phases'].setdefault(phase, {'status': 'FAILED', 'failure_class': type(exc).__name__})
        if isinstance(exc, SourceError):
            report['failure']['reason'] = str(exc)
        return 2
    finally:
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['not_run'] = [p for p in ('source_preflight', 'overlap_revision_check', 'frozen_capture', 'capture_quality', 'parquet',
                                        'official_binary', 'native_study') if p not in report['phases']]
        save()
        print(json.dumps({'status': report['status'], 'execution_record': str(run / 'execution.json')}))


if __name__ == '__main__':
    raise SystemExit(main())
