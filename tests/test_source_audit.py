import unittest
from datetime import date
from unittest.mock import patch

from ashare_quant_lab.source_audit import audit_source
from ashare_quant_lab.market_ingest import _sessions
from ashare_quant_lab.tushare_source import SourceError


class AuditTests(unittest.TestCase):
    def test_missing_credentials_reports_all_apis_not_requested(self):
        with patch.dict('os.environ', {}, clear=True):
            report = audit_source(date(2026, 1, 5), date(2026, 1, 6))
        self.assertEqual(report['status'], 'BLOCKED_CREDENTIAL_CONFIGURATION')
        self.assertEqual(set(report['apis']), {'daily', 'adj_factor', 'trade_cal'})
        self.assertTrue(all(r['status'] == 'NOT_REQUESTED' for r in report['apis'].values()))

    def test_internal_calendar_hole_is_rejected(self):
        class Source:
            def query(self, *args, **kwargs):
                return [{'cal_date': '20260105', 'is_open': 1}, {'cal_date': '20260107', 'is_open': 1}]
        with self.assertRaisesRegex(SourceError, 'incomplete'):
            _sessions(Source(), date(2026, 1, 5), date(2026, 1, 7))
