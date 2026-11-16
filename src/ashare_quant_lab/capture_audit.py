"""Private source-response preservation and cross-field capture quality audit."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .market_store import connect_store
from .tushare_source import SourceError, parse_day, valid_number


class RecordingSource:
    """Keep licensed responses only in the explicitly selected private directory."""
    def __init__(self, client, directory: Path):
        self.client, self.directory = client, directory
        directory.mkdir(parents=True, exist_ok=False)
        self.records = []

    def query(self, api_name, **params):
        rows = self.client.query(api_name, **params)
        data = json.dumps(rows, sort_keys=True).encode()
        filename = f'{len(self.records):04d}-{api_name}.json'
        (self.directory / filename).write_bytes(data)
        self.records.append({'file': filename, 'api': api_name, 'params': params,
                             'rows': len(rows), 'sha256': hashlib.sha256(data).hexdigest()})
        (self.directory / 'manifest.json').write_text(json.dumps(self.records, indent=2) + '\n')
        return rows


def audit_recorded_capture(database, capture_id, source):
    """Reconcile raw API units and ex-right pre_close against cumulative factors.

    Missing open days remain unclassified. Cross-field agreement is a source
    consistency test, not independent verification of dividends or availability.
    """
    result = {'capture_id': capture_id, 'symbols': [], 'source_record_count': len(source.records),
              'status': 'SOURCE_INTERNAL_CONSISTENCY_CHECKED_NOT_CORPORATE_ACTION_PROOF'}
    for record in source.records:
        if hashlib.sha256((source.directory / record['file']).read_bytes()).hexdigest() != record['sha256']:
            raise SourceError('recorded source response hash mismatch')
    with connect_store(database, read_only=True) as conn:
        szse_records = [r for r in source.records if r['api'] == 'trade_cal' and r['params'].get('exchange') == 'SZSE']
        result['exchange_calendar_comparison'] = 'NOT_REQUESTED'
        if szse_records:
            record = szse_records[-1]
            raw_calendar = json.loads((source.directory / record['file']).read_text())
            if any(str(r.get('is_open')) not in ('0', '1') for r in raw_calendar):
                raise SourceError('invalid SZSE calendar status')
            szse = [(parse_day(r['cal_date']), str(r['is_open']) == '1') for r in raw_calendar]
            sse = conn.execute('SELECT cal_date, is_open FROM trade_sessions WHERE capture_id=? ORDER BY cal_date', [capture_id]).fetchall()
            if sorted(szse) != sse:
                raise SourceError('SSE and SZSE source calendars disagree')
            result['exchange_calendar_comparison'] = 'SSE_SZSE_MATCH'
        symbols = conn.execute('SELECT DISTINCT symbol FROM daily_bars WHERE capture_id=? ORDER BY symbol', [capture_id]).fetchall()
        for (symbol,) in symbols:
            rows = conn.execute('''SELECT trade_date, close, volume_shares, amount_cny, cumulative_factor
                FROM daily_bars WHERE capture_id=? AND symbol=? ORDER BY trade_date''', [capture_id, symbol]).fetchall()
            raw = {}
            for record in source.records:
                if record['api'] == 'daily' and record['params'].get('ts_code') == symbol:
                    path = source.directory / record['file']
                    if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                        raise SourceError('recorded source response hash mismatch')
                    for r in json.loads(path.read_text()):
                        raw[parse_day(r['trade_date'])] = r
            units, factors, missing_reference, event_count = [], [], [], 0
            previous = None
            for day, close, volume, amount, factor in rows:
                if day not in raw:
                    raise SourceError('recorded daily response missing capture key')
                r = raw[day]
                if not (math.isclose(valid_number(r['vol']) * 100, volume)
                        and math.isclose(valid_number(r['amount']) * 1000, amount)
                        and math.isclose(valid_number(r['close']), close)):
                    raise SourceError('raw response and stored units/prices disagree')
                if volume <= 0 or not valid_number(r['low']) * .98 <= amount / volume <= valid_number(r['high']) * 1.02:
                    units.append(str(day))
                if previous is not None:
                    prior_close, prior_factor = previous
                    ratio = factor / prior_factor
                    event_count += int(not math.isclose(ratio, 1, rel_tol=1e-8))
                    if r.get('pre_close') is None:
                        missing_reference.append(str(day))
                    else:
                        reconstructed = valid_number(r['pre_close'], positive=True) * ratio
                        # Source rounds ex-right reference prices to cents.
                        if not math.isclose(reconstructed, prior_close, rel_tol=.001, abs_tol=.02 * max(1, ratio)):
                            factors.append(str(day))
                previous = close, factor
            result['symbols'].append({'symbol': symbol, 'bars': len(rows), 'factor_change_events': event_count,
                                       'unit_vwap_outliers': units, 'factor_reference_outliers': factors,
                                       'missing_pre_close_reference': missing_reference})
    result['outlier_count'] = sum(len(r[k]) for r in result['symbols']
                                  for k in ('unit_vwap_outliers', 'factor_reference_outliers', 'missing_pre_close_reference'))
    if result['outlier_count']:
        result['status'] = 'REQUIRES_SOURCE_QUALITY_REVIEW'
    return result
