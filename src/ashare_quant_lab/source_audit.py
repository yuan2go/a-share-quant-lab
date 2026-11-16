"""Credential-safe three-API preflight; responses stay in process, not reports."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from .market_ingest import _sessions
from .tushare_source import TushareClient, SourceError, parse_day, valid_number


def audit_source(start: date, end: date, symbol='600519.SH'):
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'range': [str(start), str(end)], 'symbol': symbol,
              'apis': {}, 'historical_PIT_qualified': False,
              'unit_contract': {'daily_vol': 'hands -> shares * 100',
                                'daily_amount': 'thousand CNY -> CNY * 1000',
                                'adj_factor': 'cumulative; not an event ratio'}}
    try:
        client = TushareClient()
    except SourceError as exc:
        report.update(status='BLOCKED_CREDENTIAL_CONFIGURATION', reason=str(exc))
        report['apis'] = {api: {'status': 'NOT_REQUESTED'} for api in ('trade_cal', 'daily', 'adj_factor')}
        return report
    responses = {}
    for api in ('trade_cal', 'daily', 'adj_factor'):
        params = {'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d')}
        params.update({'exchange': 'SSE'} if api == 'trade_cal' else {'ts_code': symbol})
        try:
            rows = client.query(api, **params)
            responses[api] = rows
            report['apis'][api] = {'status': 'RECEIVED' if rows else 'EMPTY', 'rows': len(rows),
                                  'response_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
        except SourceError as exc:
            report['apis'][api] = {'status': 'FAILED', 'reason': str(exc)}
    if len(responses) != 3 or any(not rows for rows in responses.values()):
        report['status'] = 'BLOCKED_SOURCE_API'
        return report
    # Reuse ingestion validation on exactly these responses, avoiding another request.
    class RecordedSource:
        def query(self, api_name, **kwargs):
            return responses[api_name]
    from .tushare_source import daily_rows, factor_snapshots
    try:
        sessions = _sessions(RecordedSource(), start, end)
        bars = daily_rows(RecordedSource(), symbol, start, end)
        factors = factor_snapshots(RecordedSource(), symbol, start, end)
        opened = {d.isoformat() for d, is_open in sessions if is_open}
        days = {b['trade_date'] for b in bars}
        if not days <= opened or not days <= set(factors):
            raise SourceError('daily/calendar/factor coverage disagreement')
        # Independent dimensional check: VWAP after the documented conversion
        # must fall inside that day's raw price interval (allow source rounding).
        unit_bad = 0
        raw_by_day = {parse_day(r['trade_date']).isoformat(): r for r in responses['daily']}
        for bar in bars:
            raw = raw_by_day[bar['trade_date']]
            vol = valid_number(raw['vol'], positive=True) * 100
            amount = valid_number(raw['amount'], positive=True) * 1000
            if not bar['low'] * .98 <= amount / vol <= bar['high'] * 1.02:
                unit_bad += 1
        report['coverage'] = {'open_sessions': len(opened), 'daily_rows': len(days),
                              'missing_open_dates_unclassified': sorted(opened - days),
                              'missing_factors_for_bars': sorted(days - set(factors)),
                              'unit_vwap_outside_ohlc_2pct_tolerance': unit_bad}
        if unit_bad:
            raise SourceError('source unit/VWAP dimensional check failed')
        report['status'] = 'RECEIVED_AND_DIMENSIONALLY_VALIDATED_NOT_PIT'
    except (SourceError, KeyError, ValueError) as exc:
        report.update(status='BLOCKED_SOURCE_QUALITY', reason=str(exc) if isinstance(exc, SourceError) else type(exc).__name__)
    return report
