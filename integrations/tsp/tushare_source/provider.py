"""Tushare-compatible adapter for TSP's existing source plugin contract."""

from __future__ import annotations
from datetime import date, datetime, timedelta
import logging
from types import SimpleNamespace
import polars as pl
from app import secrets_store
from app.config import settings
from app.data_providers.base import ProviderRequestError
from .client import Client, SourceError
from .normalize import (
    daily,
    events,
    realtime,
    day,
    number,
    completed_calendar_day,
    latest_reports,
)

log = logging.getLogger(__name__)


def availability():
    return (
        bool(
            secrets_store.get_env_backed_secret("aql_tushare_api_key", "TUSHARE_TOKEN")
        ),
        "通过环境/本机密钥配置Tushare；分钟/盘口未声明",
    )


def probe_api_key(key):
    try:
        Client(key, settings.data_dir / "provider_cache/aql_tushare").query(
            "trade_cal", exchange="SSE", start_date="20261101", end_date="20261116"
        )
        return True, "交易日历可访问；各数据集需分别验证"
    except Exception:
        return False, "源验证失败（凭据/权限/网络），无上游正文输出"


class Provider:
    name = "aql_tushare"

    def __init__(self):
        self.config = SimpleNamespace(
            datasets={k: {} for k in ["daily", "adj_factor", "financial"]}
        )
        key = secrets_store.get_env_backed_secret(
            "aql_tushare_api_key", "TUSHARE_TOKEN"
        )
        self.client = Client(key, settings.data_dir / "provider_cache/aql_tushare")
        self._inst = {}

    def close(self):
        pass

    def _frame(self, rows):
        return pl.from_dicts(rows, infer_schema_length=None) if rows else pl.DataFrame()

    def get_instruments(self, asset_type="stock"):
        if asset_type in self._inst:
            return self._inst[asset_type]
        if asset_type == "stock":
            raw = self.client.all(
                "stock_basic",
                list_status="L",
                fields="ts_code,symbol,name,area,industry,market,list_date",
            )
            basics = {
                r["ts_code"]: r
                for r in self.client.all(
                    "daily_basic",
                    trade_date=self._latest_day().strftime("%Y%m%d"),
                    fields="ts_code,trade_date,total_share,float_share",
                )
            }
            result = []
            for r in raw:
                b = basics.get(r["ts_code"], {})
                result.append(
                    {
                        "symbol": r["ts_code"],
                        "code": r["ts_code"].split(".")[0],
                        "name": r["name"],
                        "exchange": r["ts_code"].split(".")[1],
                        "region": "CN",
                        "type": "stock",
                        "ext": {
                            "listing_date": (
                                str(day(r["list_date"])) if r.get("list_date") else None
                            ),
                            "total_shares": (
                                number(b.get("total_share"), optional=True) * 10000
                                if b.get("total_share") is not None
                                else None
                            ),
                            "float_shares": (
                                number(b.get("float_share"), optional=True) * 10000
                                if b.get("float_share") is not None
                                else None
                            ),
                            "tick_size": 0.01,
                        },
                    }
                )
        elif asset_type == "etf":
            raw = self.client.all("fund_basic", market="E", status="L")
            result = [
                {
                    "symbol": r["ts_code"],
                    "code": r["ts_code"].split(".")[0],
                    "name": r["name"],
                    "exchange": r["ts_code"].split(".")[1],
                    "type": "etf",
                    "region": "CN",
                    "ext": {
                        "listing_date": (
                            str(day(r["list_date"])) if r.get("list_date") else None
                        )
                    },
                }
                for r in raw
                if "ETF" in (r.get("name") or "").upper()
            ]
        elif asset_type == "index":
            core = {
                "000001.SH": "上证指数",
                "399001.SZ": "深证成指",
                "399006.SZ": "创业板指",
                "000680.SH": "科创综指",
            }
            result = [
                {
                    "symbol": s,
                    "code": s.split(".")[0],
                    "name": n,
                    "exchange": s.split(".")[1],
                    "type": "index",
                    "region": "CN",
                    "ext": {},
                }
                for s, n in core.items()
            ]
        else:
            raise ProviderRequestError("unsupported asset type")
        self._inst[asset_type] = result
        return result

    def _latest_day(self):
        from zoneinfo import ZoneInfo

        today = completed_calendar_day(datetime.now(ZoneInfo("Asia/Shanghai")))
        rows = self.client.query(
            "trade_cal",
            exchange="SSE",
            start_date=(today - timedelta(days=15)).strftime("%Y%m%d"),
            end_date=today.strftime("%Y%m%d"),
        )
        opened = [day(r["cal_date"]) for r in rows if str(r["is_open"]) == "1"]
        return max(opened)

    def iter_daily(
        self, symbols, start_time, end_time, asset_type="stock", on_chunk_done=None
    ):
        end = day(end_time) if end_time is not None else self._latest_day()
        start = day(start_time) if start_time is not None else end - timedelta(days=365)
        wanted = set(symbols)
        api = {"stock": "daily", "index": "index_daily", "etf": "fund_daily"}.get(
            asset_type
        )
        if not api:
            raise ProviderRequestError("unsupported daily asset type")
        try:
            if asset_type == "stock" and len(wanted) > 100:
                dates = self.client.query(
                    "trade_cal",
                    exchange="SSE",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
                dates = sorted(
                    day(r["cal_date"]) for r in dates if str(r["is_open"]) == "1"
                )
                for i, d in enumerate(dates):
                    rows = self.client.all(api, trade_date=d.strftime("%Y%m%d"))
                    frame = self._frame(
                        daily([r for r in rows if r["ts_code"] in wanted])
                    )
                    if not frame.is_empty():
                        yield frame
                    if on_chunk_done:
                        on_chunk_done(i + 1, len(dates))
            else:
                for i, symbol in enumerate(sorted(wanted)):
                    rows = self.client.all(
                        api,
                        ts_code=symbol,
                        start_date=start.strftime("%Y%m%d"),
                        end_date=end.strftime("%Y%m%d"),
                    )
                    if any(
                        r["ts_code"] != symbol
                        or not start <= day(r["trade_date"]) <= end
                        for r in rows
                    ):
                        raise SourceError("daily key outside request")
                    frame = self._frame(daily(rows))
                    if not frame.is_empty():
                        yield frame
                    if on_chunk_done:
                        on_chunk_done(i + 1, len(wanted))
        except (SourceError, ValueError, KeyError) as exc:
            raise ProviderRequestError(
                f"daily source failed: {type(exc).__name__}"
            ) from None

    def get_daily(
        self, symbols, start_time, end_time, asset_type="stock", on_chunk_done=None
    ):
        frames = list(
            self.iter_daily(symbols, start_time, end_time, asset_type, on_chunk_done)
        )
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_adj_factors(
        self, symbols, start_time, end_time, asset_type="stock", on_chunk_done=None
    ):
        if asset_type == "index":
            return pl.DataFrame()
        end = day(end_time) if end_time is not None else self._latest_day()
        if start_time is None and len(symbols) > 100:
            files = list((settings.data_dir / "kline_daily").glob("**/*.parquet"))
            if not files:
                raise ProviderRequestError("全市场因子同步前请先同步日K")
            start = pl.scan_parquet(files).select(pl.col("date").min()).collect().item()
        else:
            start = day(start_time) if start_time is not None else date(1990, 1, 1)
        earlier = max(date(1990, 1, 1), start - timedelta(days=60))
        api = "fund_adj" if asset_type == "etf" else "adj_factor"
        wanted = set(symbols)
        raw = []
        try:
            if len(wanted) > 100:
                dates = self.client.query(
                    "trade_cal",
                    exchange="SSE",
                    start_date=earlier.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
                opened = sorted(
                    day(r["cal_date"]) for r in dates if str(r["is_open"]) == "1"
                )
                before = [d for d in opened if d < start]
                requested = ([before[-1]] if before else []) + [
                    d for d in opened if d >= start
                ]
                previous = {}
                converted = []
                for i, d in enumerate(requested):
                    chunk = [
                        r
                        for r in self.client.all(api, trade_date=d.strftime("%Y%m%d"))
                        if r["ts_code"] in wanted
                    ]
                    if any(day(r["trade_date"]) != d for r in chunk):
                        raise SourceError("factor date outside request")
                    converted.extend(events(chunk, start, previous))
                    if on_chunk_done:
                        on_chunk_done(i + 1, len(requested))
                return self._frame(converted)
            else:
                for i, symbol in enumerate(sorted(wanted)):
                    raw.extend(
                        self.client.all(
                            api,
                            ts_code=symbol,
                            start_date=earlier.strftime("%Y%m%d"),
                            end_date=end.strftime("%Y%m%d"),
                        )
                    )
                    if on_chunk_done:
                        on_chunk_done(i + 1, len(wanted))
            return self._frame(events(raw, start))
        except (SourceError, ValueError, KeyError) as exc:
            raise ProviderRequestError(
                f"adjustment source failed: {type(exc).__name__}"
            ) from None

    def get_realtime(self):
        try:
            raw = []
            for pattern in ["6*.SH", "0*.SZ", "3*.SZ", "9*.BJ", "4*.BJ", "8*.BJ"]:
                raw.extend(
                    self.client.query(
                        "rt_k",
                        ts_code=pattern,
                        fields="ts_code,name,pre_close,high,open,low,close,vol,amount,trade_time",
                        refresh=True,
                    )
                )
            unique = {r["ts_code"]: r for r in raw}
            return realtime(list(unique.values()), require_timestamp=True)
        except (SourceError, ValueError, KeyError) as exc:
            log.warning("Tushare RT unavailable: %s", type(exc).__name__)
            return []

    def get_realtime_symbols(self, symbols, *, asset_type="stock"):
        if asset_type != "stock":
            return []
        try:
            return realtime(
                self.client.query(
                    "rt_k",
                    ts_code=",".join(symbols),
                    fields="ts_code,name,pre_close,high,open,low,close,vol,amount,trade_time",
                    refresh=True,
                ),
                require_timestamp=True,
            )
        except (SourceError, ValueError, KeyError):
            return None

    def get_financials(self, table, symbols, latest_only=False):
        api = {
            "metrics": "fina_indicator",
            "income": "income",
            "balance_sheet": "balancesheet",
            "cash_flow": "cashflow",
        }.get(table)
        if table == "shares":
            end = self._latest_day()
            raw = self.client.all(
                "daily_basic",
                trade_date=end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,total_share,float_share",
            )
            wanted = set(symbols)
            # daily_basic is a contemporaneous observation, not an announcement
            # history. Never invent an announce_date from trade_date.
            return self._frame(
                [
                    {
                        "symbol": r["ts_code"],
                        "period_end": day(r["trade_date"]),
                        "announce_date": None,
                        "total_shares": number(r["total_share"]) * 10000,
                        "float_shares": number(r["float_share"]) * 10000,
                    }
                    for r in raw
                    if r["ts_code"] in wanted
                    and r.get("total_share") is not None
                    and r.get("float_share") is not None
                ]
            )
        if not api:
            raise ProviderRequestError("unsupported financial table")
        mapping = {
            "metrics": {
                "eps": "eps_basic",
                "bps": "bps",
                "ocfps": "ocfps",
                "roe": "roe",
                "roa": "roa",
                "grossprofit_margin": "gross_margin",
                "netprofit_margin": "net_margin",
                "debt_to_assets": "debt_to_asset_ratio",
                "tr_yoy": "revenue_yoy",
                "netprofit_yoy": "net_income_yoy",
            },
            "income": {
                "revenue": "revenue",
                "oper_cost": "operating_cost",
                "operate_profit": "operating_profit",
                "sell_exp": "selling_expense",
                "admin_exp": "admin_expense",
                "rd_exp": "rd_expense",
                "fin_exp": "financial_expense",
                "non_oper_income": "non_operating_income",
                "non_oper_exp": "non_operating_expense",
                "total_profit": "total_profit",
                "income_tax": "income_tax",
                "n_income": "net_income",
                "n_income_attr_p": "net_income_attributable",
                "basic_eps": "basic_eps",
                "diluted_eps": "diluted_eps",
            },
            "balance_sheet": {
                "total_assets": "total_assets",
                "total_cur_assets": "total_current_assets",
                "total_nca": "total_non_current_assets",
                "money_cap": "cash_and_equivalents",
                "accounts_receiv": "accounts_receivable",
                "inventories": "inventory",
                "fix_assets": "fixed_assets",
                "intan_assets": "intangible_assets",
                "goodwill": "goodwill",
                "total_liab": "total_liabilities",
                "total_cur_liab": "total_current_liabilities",
                "total_ncl": "total_non_current_liabilities",
                "st_borr": "short_term_borrowing",
                "lt_borr": "long_term_borrowing",
                "acct_payable": "accounts_payable",
                "total_hldr_eqy_inc_min_int": "total_equity",
                "total_hldr_eqy_exc_min_int": "equity_attributable",
                "minority_int": "minority_interest",
            },
            "cash_flow": {
                "n_cashflow_act": "net_operating_cash_flow",
                "n_cashflow_inv_act": "net_investing_cash_flow",
                "n_cash_flows_fnc_act": "net_financing_cash_flow",
                "c_pay_acq_const_fiolta": "capex",
                "n_incr_cash_cash_equ": "net_cash_change",
            },
        }[table]
        raw = []
        if len(symbols) > 100:
            from zoneinfo import ZoneInfo

            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            periods = [
                date(y, m, d)
                for y in range(today.year - 2, today.year + 1)
                for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]
                if date(y, m, d) <= today
            ]
            for period in periods:
                raw.extend(
                    self.client.all(api + "_vip", period=period.strftime("%Y%m%d"))
                )
        else:
            for symbol in symbols:
                raw.extend(
                    self.client.all(
                        api,
                        ts_code=symbol,
                        start_date=(self._latest_day() - timedelta(days=1100)).strftime(
                            "%Y%m%d"
                        ),
                    )
                )
        wanted = set(symbols)
        rows = []
        for r in raw:
            if r.get("ts_code") not in wanted or not r.get("end_date"):
                continue
            if table != "metrics" and str(r.get("report_type")) != "1":
                continue  # Consolidated cumulative statements only.
            ann = r.get("f_ann_date") or r.get("ann_date")
            rows.append(
                {
                    "symbol": r["ts_code"],
                    "period_end": day(r["end_date"]),
                    "announce_date": day(ann) if ann else None,
                    "_update_flag": r.get("update_flag"),
                    **{
                        target: (
                            number(r[source], optional=True) if source in r else None
                        )
                        for source, target in mapping.items()
                    },
                }
            )
        df = self._frame(latest_reports(rows))
        if latest_only and not df.is_empty():
            df = df.sort(
                ["symbol", "period_end", "announce_date"], nulls_last=False
            ).unique(subset=["symbol"], keep="last")
        return df

    def test_dataset(self, dataset, symbols=None):
        symbols = symbols or ["000001.SZ"]
        end = self._latest_day()
        start = end - timedelta(days=14)
        try:
            if dataset == "daily":
                frame = self.get_daily(symbols, start, end)
            elif dataset == "adj_factor":
                frame = self.get_adj_factors(symbols, start, end)
            elif dataset == "financial":
                frame = self.get_financials("metrics", symbols)
            elif dataset == "realtime":
                frame = self._frame(self.get_realtime_symbols(symbols) or [])
            else:
                return {
                    "provider": self.name,
                    "dataset": dataset,
                    "error": "此数据集未获得授权/未实现",
                    "rows": 0,
                }
            return {
                "provider": self.name,
                "dataset": dataset,
                "rows": frame.height,
                "columns": frame.columns,
                "preview": [],
            }
        except Exception as exc:
            return {
                "provider": self.name,
                "dataset": dataset,
                "rows": 0,
                "error": type(exc).__name__,
            }
