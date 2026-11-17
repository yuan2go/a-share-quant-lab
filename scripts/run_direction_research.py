"""Official repository workflow for real direction research; all data stays private.

Use existing authorized environment credentials. Each phase refuses to overwrite
its outputs; failed execution records remain alongside later phase attempts.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import tempfile
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--qlib-repo', type=Path, required=True)
    parser.add_argument('--historical-run', type=Path, required=True,
                        help='Existing frozen first-study capture with parquet/ and binary/')
    parser.add_argument('--phase', choices=['prepare', 'study', 'latest', 'all'], default='all')
    args = parser.parse_args()
    root = args.run_dir.resolve()
    if not str(root).startswith('/Volumes/'):
        parser.error('real data, cache and logs require external /Volumes/ storage')
    root.mkdir(parents=True, exist_ok=True)
    (root / 'tmp').mkdir(exist_ok=True)
    os.environ['TMPDIR'] = str(root / 'tmp')
    tempfile.tempdir = str(root / 'tmp')
    os.environ['MPLCONFIGDIR'] = str(root / 'cache/matplotlib')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from ashare_quant_lab.direction_data import digest, write_json
    from ashare_quant_lab.direction_study import run_direction_study, train_latest
    from ashare_quant_lab.direction_inference import infer_direction, review_direction
    from ashare_quant_lab.capture_audit import RecordingSource, audit_recorded_capture
    from ashare_quant_lab.market_ingest import ingest_market
    from ashare_quant_lab.market_export import export_market_parquet
    from ashare_quant_lab.qlib_dump import dump_parquet_using_official_qlib
    from ashare_quant_lab.symbols import load_symbols
    from ashare_quant_lab.tushare_source import TushareClient, SourceError, parse_day
    repo = Path(__file__).resolve().parents[1]
    config = repo / 'configs/direction-study.json'
    execution = root / ('execution-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.json')
    state = {'work_package': 'WP-AQL-DIRECTION-FORECAST-01', 'phase': args.phase, 'status': 'RUNNING',
             'started_at': datetime.now(timezone.utc).isoformat(), 'phases': {}}
    try:
        if args.phase in ('prepare', 'all'):
            # A new isolated capture file avoids locks/writes on any existing reader or service.
            if (root / 'market.duckdb').exists():
                raise FileExistsError('capture path exists; choose a new run directory')
            source = RecordingSource(TushareClient(), root / 'source-responses')
            now = datetime.now(timezone.utc)
            local = now.astimezone(ZoneInfo('Asia/Shanghai'))
            start = local.date() - timedelta(days=30)
            end = local.date() + timedelta(days=50)
            calendars = [source.query('trade_cal', exchange=exchange, start_date=start.strftime('%Y%m%d'),
                                      end_date=end.strftime('%Y%m%d')) for exchange in ('SSE', 'SZSE')]
            def parse(rows):
                expected = {start + timedelta(days=i) for i in range((end - start).days + 1)}
                parsed = [(parse_day(r['cal_date']), str(r['is_open'])) for r in rows]
                if len(parsed) != len(expected) or {d for d, _ in parsed} != expected or any(s not in ('0', '1') for _, s in parsed):
                    raise SourceError('source calendar missing, duplicate or invalid dates')
                return sorted(parsed)
            if parse(calendars[0]) != parse(calendars[1]):
                raise SourceError('source exchange calendars disagree')
            open_dates = [d for d, s in parse(calendars[0]) if s == '1']
            bound = local.date() if local.hour >= 15 else local.date() - timedelta(days=1)
            completed = max(d for d in open_dates if d <= bound)
            write_json(root / 'calendar-clock.json', {'captured_at': now.isoformat(), 'exchanges': 'SSE_SZSE_MATCH',
                       'range_start': start.isoformat(), 'range_end': end.isoformat(),
                       'open_dates': [d.isoformat() for d in open_dates]})
            cohort = load_symbols(repo / 'configs/first-study-cohort.txt')
            capture = ingest_market(root / 'market.duckdb', source, cohort, date(2019, 1, 2), completed, pace_seconds=1)
            state['phases']['capture'] = capture
            # Full source-calendar audit requires the matching SZSE history.
            source.query('trade_cal', exchange='SZSE', start_date='20190102', end_date=completed.strftime('%Y%m%d'))
            quality = audit_recorded_capture(root / 'market.duckdb', capture['capture_id'], source)
            write_json(root / 'capture-quality.json', quality)
            if quality['outlier_count']:
                raise SourceError('source consistency outliers require diagnosis')
            state['phases']['parquet'] = export_market_parquet(root / 'market.duckdb', cohort, date(2019, 1, 2),
                                                                completed, root / 'parquet', capture_id=capture['capture_id'])
            state['phases']['binary'] = dump_parquet_using_official_qlib(args.qlib_repo, root / 'parquet', root / 'binary')
        if args.phase in ('study', 'all'):
            historical = args.historical_run.resolve()
            state['phases']['study'] = run_direction_study(historical / 'binary', historical / 'parquet/manifest.json',
                                                          config, root / 'study')
        if args.phase in ('latest', 'all'):
            latest = train_latest(root / 'binary', root / 'parquet/manifest.json', config, root / 'latest-training')
            state['phases']['latest_model'] = latest
            state['phases']['inference'] = infer_direction(root / 'binary', root / 'parquet/manifest.json',
                     Path(latest['model_dir']), latest['model_record_sha256'], root / 'calendar-clock.json', root / 'prediction.json')
            state['phases']['review'] = review_direction(root / 'prediction.json', root / 'binary',
                                                         root / 'parquet/manifest.json', root / 'initial-review.json')
        state['status'] = 'PHASE_COMPLETE_NOT_TRADING_QUALIFIED'
        return 0
    except Exception as exc:
        state.update(status='FAILED', failure_class=type(exc).__name__)
        # Private diagnostic only; never echo source bodies or credentials.
        (root / (execution.stem + '-failure.txt')).write_text(traceback.format_exc())
        return 2
    finally:
        state['completed_at'] = datetime.now(timezone.utc).isoformat()
        write_json(execution, state)
        print(json.dumps({'status': state['status'], 'execution_record': str(execution)}))


if __name__ == '__main__':
    raise SystemExit(main())
