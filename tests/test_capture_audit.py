import tempfile
import unittest
from datetime import date
from pathlib import Path

from ashare_quant_lab.capture_audit import RecordingSource, audit_recorded_capture
from ashare_quant_lab.market_ingest import ingest_market


class CaptureAuditTests(unittest.TestCase):
    def test_response_units_and_exright_factor_are_reconciled(self):
        class Source:
            def __init__(self, bad_factor):
                self.bad_factor = bad_factor
            def query(self, api_name, **params):
                if api_name == 'trade_cal':
                    return [{'cal_date': d, 'is_open': 1} for d in ['20260105', '20260106']]
                if api_name == 'adj_factor':
                    return [{'ts_code': '600519.SH', 'trade_date': d, 'adj_factor': f} for d, f in
                            [('20260105', 1), ('20260106', 3 if self.bad_factor else 2)]]
                return [{'ts_code': '600519.SH', 'trade_date': d, 'open': p, 'close': p,
                         'high': p, 'low': p, 'pre_close': p, 'vol': 100, 'amount': p * 10}
                        for d, p in [('20260105', 100), ('20260106', 50)]]
        for bad in (False, True):
            with self.subTest(bad_factor=bad), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = RecordingSource(Source(bad), root / 'responses')
                capture = ingest_market(root / 'market.duckdb', source, ['600519.SH'],
                                        date(2026, 1, 5), date(2026, 1, 6))
                source.query('trade_cal', exchange='SZSE')
                audit = audit_recorded_capture(root / 'market.duckdb', capture['capture_id'], source)
                self.assertEqual(audit['outlier_count'], int(bad))
                self.assertEqual(len(source.records), 4)
                self.assertEqual(audit['exchange_calendar_comparison'], 'SSE_SZSE_MATCH')
