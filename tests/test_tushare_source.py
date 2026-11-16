import json
import gzip
import unittest
from datetime import date
from unittest.mock import patch
from io import BytesIO

from ashare_quant_lab.tushare_source import (
    SourceError, TushareClient, daily_rows, tsp_factor_events
)
from ashare_quant_lab.tsp_gateway import handle_request


class FakeSource:
    def query(self, api_name, **params):
        if api_name == "daily":
            return [
                {"ts_code": "000001.SZ", "trade_date": "20261112", "open": 10, "high": 11,
                 "low": 9, "close": 10.5, "vol": 100, "amount": 2200},
            ]
        if api_name == "adj_factor":
            return [
                {"ts_code": "000001.SZ", "trade_date": "20261110", "adj_factor": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "20261111", "adj_factor": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "20261112", "adj_factor": 2.0},
                {"ts_code": "000001.SZ", "trade_date": "20261113", "adj_factor": 2.0},
            ]
        raise AssertionError("unexpected API")


class NormalizationTests(unittest.TestCase):
    def test_core_client_negotiates_and_decodes_gzip(self):
        payload={'code':0,'data':{'fields':['cal_date','is_open'],'items':[['20261116',1]]}}
        class Response(BytesIO):
            status=200
            headers={'Content-Encoding':'gzip'}
        def open_request(request,**kwargs):
            self.assertEqual(request.get_header('Accept-encoding'),'gzip')
            return Response(gzip.compress(json.dumps(payload).encode()))
        with patch('urllib.request.urlopen',side_effect=open_request):
            rows=TushareClient(token='synthetic').query('trade_cal',start_date='20261116')
        self.assertEqual(rows,[{'cal_date':'20261116','is_open':1}])

    def test_daily_units_ohlc_and_dates(self):
        data = daily_rows(FakeSource(), "000001.SZ", date(2026, 11, 12), date(2026, 11, 13))
        self.assertEqual(data[0]["trade_date"], "2026-11-12")
        self.assertEqual(data[0]["vol"], 10000)
        self.assertEqual(data[0]["amt"], 2_200_000)

    def test_cumulative_adj_to_event_ratio(self):
        events = tsp_factor_events(FakeSource(), "000001.SZ", date(2026, 11, 11), date(2026, 11, 13))
        self.assertEqual(events, [{"ts_code": "000001.SZ", "trade_date": "2026-11-12", "factor": 2.0}])

    def test_gateway_unsupported_asset_does_not_silently_fallback(self):
        with self.assertRaisesRegex(ValueError, "stock"):
            handle_request(FakeSource(), "/daily", {
                "symbols": ["000001.SZ"], "start_time": "2026-11-12", "end_time": "2026-11-13", "asset_type": "etf"
            })

    def test_missing_prewindow_factor_hard_fails(self):
        class MissingPrior(FakeSource):
            def query(self, api_name, **params):
                if api_name == "adj_factor":
                    return [{"ts_code": "000001.SZ", "trade_date": "20261112", "adj_factor": 2}]
                return super().query(api_name, **params)
        with self.assertRaisesRegex(SourceError, "baseline"):
            tsp_factor_events(MissingPrior(), "000001.SZ", date(2026, 11, 12), date(2026, 11, 13))

    def test_missing_credentials_fail_closed(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(SourceError, "TUSHARE_TOKEN"):
                TushareClient()


if __name__ == "__main__":
    unittest.main()
