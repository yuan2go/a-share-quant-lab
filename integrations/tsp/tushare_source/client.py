"""Bounded, credential-safe Tushare HTTP transport with private response cache."""

from __future__ import annotations
import hashlib
import gzip
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

APIS = frozenset(
    {
        "trade_cal",
        "stock_basic",
        "daily",
        "daily_basic",
        "adj_factor",
        "index_daily",
        "index_basic",
        "fund_basic",
        "fund_daily",
        "fund_adj",
        "rt_k",
        "fina_indicator",
        "income",
        "balancesheet",
        "cashflow",
        "fina_indicator_vip",
        "income_vip",
        "balancesheet_vip",
        "cashflow_vip",
        "ths_index",
        "ths_member",
        "ths_daily",
    }
)


class SourceError(RuntimeError):
    pass


class Client:
    def __init__(
        self,
        token,
        cache_dir: Path,
        *,
        url=None,
        interval=1.5,
        timeout=30,
        max_cache_age=86400,
    ):
        if not token:
            raise SourceError("TUSHARE_TOKEN missing")
        self.token = token
        self.url = url or os.getenv("TUSHARE_HTTP_URL", "https://t.xiaodefa.top/")
        if not self.url.startswith("https://") or "?" in self.url or "@" in self.url:
            raise SourceError("source must be credential-free HTTPS URL")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.interval, self.timeout = interval, timeout
        self.max_cache_age = max_cache_age
        self.lock = threading.Lock()
        self.last = 0
        self.cooldown_until = 0

    def query(self, api, *, fields="", refresh=False, **params):
        if api not in APIS:
            raise SourceError("unsupported source API")
        identity = json.dumps(
            [api, fields, params], sort_keys=True, separators=(",", ":")
        )
        path = self.cache / (hashlib.sha256(identity.encode()).hexdigest() + ".json")
        if not refresh and path.exists():
            data = json.loads(path.read_text())
            if data.get("identity") != identity:
                raise SourceError("cache identity mismatch")
            age = time.time() - data.get("captured_at", 0)
            # Older 0.1.x captures are bound to this private data directory's
            # original source. New captures also record the credential-free URL.
            if (
                data.get("source_url", self.url) == self.url
                and 0 <= age < self.max_cache_age
            ):
                return data["rows"]
        for attempt in range(3):
            with self.lock:
                time.sleep(
                    max(
                        0,
                        self.interval - (time.monotonic() - self.last),
                        self.cooldown_until - time.monotonic(),
                    )
                )
                self.last = time.monotonic()
            req = urllib.request.Request(
                self.url,
                data=json.dumps(
                    {
                        "api_name": api,
                        "token": self.token,
                        "params": params,
                        "fields": fields,
                    }
                ).encode(),
                headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    body = response.read(20_000_001)
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(20_000_001)
                if len(body) > 20_000_000:
                    raise SourceError("response too large")
                payload = json.loads(body)
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                ValueError,
                EOFError,
            ) as exc:
                raise SourceError(
                    f"{api}: transport/JSON failure ({type(exc).__name__})"
                ) from None
            if (
                isinstance(payload, dict)
                and payload.get("code") == 429
                and "gzip" not in str(payload.get("msg", "")).lower()
                and attempt < 2
            ):
                with self.lock:
                    self.cooldown_until = max(
                        self.cooldown_until, time.monotonic() + 65
                    )
                continue
            break
        if (
            not isinstance(payload, dict)
            or type(payload.get("code")) is not int
            or payload["code"] != 0
        ):
            code = payload.get("code") if isinstance(payload, dict) else None
            code = code if type(code) is int else "invalid"
            raise SourceError(f"{api}: API rejected code={code}")
        data = payload.get("data") or {}
        names = data.get("fields")
        items = data.get("items")
        if (
            not isinstance(names, list)
            or not isinstance(items, list)
            or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names)
        ):
            raise SourceError(f"{api}: invalid response schema")
        if any(not isinstance(x, list) or len(x) != len(names) for x in items):
            raise SourceError(f"{api}: malformed rows")
        rows = [dict(zip(names, x)) for x in items]
        # Cache only successful provider data. Token/request bodies never persist.
        saved = {
            "source_url": self.url,
            "identity": identity,
            "api": api,
            "params": params,
            "captured_at": time.time(),
            "rows": rows,
        }
        tmp = path.with_name(path.name + "." + str(threading.get_ident()) + ".tmp")
        with tmp.open("w") as f:
            json.dump(saved, f, ensure_ascii=False, allow_nan=False)
        tmp.chmod(0o600)
        os.replace(tmp, path)
        return rows

    def pages(self, api, *, page_size=6000, max_pages=600, **params):
        previous = None
        for i in range(max_pages):
            rows = self.query(api, limit=page_size, offset=i * page_size, **params)
            digest = hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest()
            if rows and digest == previous:
                raise SourceError(f"{api}: pagination not advancing")
            previous = digest
            yield rows
            if len(rows) < page_size:
                return
        raise SourceError(f"{api}: pagination limit reached")

    def all(self, api, **params):
        return [row for page in self.pages(api, **params) for row in page]
