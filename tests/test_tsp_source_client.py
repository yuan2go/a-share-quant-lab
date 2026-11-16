import gzip
import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / "integrations/tsp/tushare_source/client.py"
spec = importlib.util.spec_from_file_location("tsp_client", P)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ClientTests(unittest.TestCase):
    def test_expired_display_cache_is_refetched(self):
        with tempfile.TemporaryDirectory() as folder:
            c = module.Client("synthetic", Path(folder), interval=0, max_cache_age=10)
            identity = json.dumps(
                ["daily", "", {"trade_date": "20261116"}],
                sort_keys=True,
                separators=(",", ":"),
            )
            import hashlib

            cache = Path(folder) / (
                hashlib.sha256(identity.encode()).hexdigest() + ".json"
            )
            cache.write_text(
                json.dumps(
                    {"identity": identity, "rows": [{"stale": True}], "captured_at": 0}
                )
            )
            with patch.object(
                module.urllib.request, "urlopen", side_effect=TimeoutError
            ):
                with self.assertRaises(module.SourceError):
                    c.query("daily", trade_date="20261116")

    def test_gzip_negotiated_and_success_cache_does_not_include_token(self):
        token = "synthetic-secret-for-test"
        payload = {"code": 0, "data": {"fields": ["ts_code"], "items": [["000001.SZ"]]}}

        class Response:
            headers = {"Content-Encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, n):
                return gzip.compress(json.dumps(payload).encode())

        def open_request(request, **kwargs):
            self.assertEqual(request.get_header("Accept-encoding"), "gzip")
            return Response()

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(
                module.urllib.request, "urlopen", side_effect=open_request
            ) as network,
        ):
            c = module.Client(token, Path(folder), interval=0)
            self.assertEqual(
                c.query("daily", trade_date="20261116"), [{"ts_code": "000001.SZ"}]
            )
            c.query("daily", trade_date="20261116")
            self.assertEqual(network.call_count, 1)
            self.assertTrue(
                all(token not in p.read_text() for p in Path(folder).glob("*.json"))
            )

    def test_pagination_that_does_not_advance_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            c = module.Client("synthetic", Path(folder), interval=0)
            with patch.object(c, "query", return_value=[{"ts_code": "000001.SZ"}]):
                with self.assertRaisesRegex(module.SourceError, "not advancing"):
                    list(c.pages("daily", page_size=1, max_pages=3))
