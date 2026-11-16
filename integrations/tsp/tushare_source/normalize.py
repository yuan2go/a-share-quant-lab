"""TSP units: daily volume in hands, RT source shares -> hands, CNY amounts."""

from datetime import datetime, date, timedelta
import math
import logging

log = logging.getLogger(__name__)


def day(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return (
        date.fromisoformat(x[:10])
        if "-" in x
        else datetime.strptime(x[:8], "%Y%m%d").date()
    )


def number(x, *, optional=False):
    if x is None and optional:
        return None
    if isinstance(x, bool):
        raise ValueError("invalid numeric value")
    v = float(x)
    if not math.isfinite(v):
        raise ValueError("nonfinite source value")
    return v


def completed_calendar_day(now):
    """Conservative EOD cutoff; trade_cal handles weekends and holidays."""
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    return local.date() if local.hour >= 18 else local.date() - timedelta(days=1)


def latest_reports(rows):
    """One complete source row per report period; never mix revision columns.

    Prefer the latest stated announcement and update flag. Equal priorities keep
    the first source row, preserving the API's ordering within this capture.
    This is a current display projection, not a historical availability claim.
    """
    selected = {}
    for row in rows:
        key = (row["symbol"], row["period_end"])
        priority = (
            row.get("announce_date") or date.min,
            str(row.get("_update_flag") or "0"),
        )
        if key not in selected or priority > selected[key][0]:
            selected[key] = (priority, row)
    return [
        {k: v for k, v in row.items() if k != "_update_flag"}
        for _, row in (selected[key] for key in sorted(selected))
    ]


def daily(rows):
    result = []
    seen = set()
    excluded = 0
    for r in rows:
        key = (r["ts_code"], day(r["trade_date"]))
        if key in seen:
            raise ValueError("duplicate daily source key")
        seen.add(key)
        prices = {k: number(r[k]) for k in ("open", "high", "low", "close")}
        vol = number(r["vol"])
        amount = number(r["amount"]) * 1000
        # The gateway includes zero-quantity rows with invalid zero OHLC values,
        # sometimes with a carried close. They are not daily bars. Keep the raw
        # response in the private cache and leave a genuine gap in TSP.
        if min(prices.values()) == 0 and vol == 0 and amount == 0:
            excluded += 1
            continue
        if min(prices.values()) <= 0 or vol < 0 or amount < 0:
            raise ValueError("invalid daily price/quantity")
        if prices["high"] < max(prices.values()) or prices["low"] > min(
            prices.values()
        ):
            raise ValueError("invalid daily OHLC")
        result.append(
            {
                "symbol": key[0],
                "date": key[1],
                **prices,
                "volume": vol,
                "amount": amount,
            }
        )
    if excluded:
        log.warning(
            "Excluded %d zero-quantity/invalid-OHLC source rows; private response retained",
            excluded,
        )
    return result


def events(rows, start, previous=None):
    # Optional state keeps full-market conversion bounded to one date batch.
    result = []
    previous = {} if previous is None else previous
    seen = set()
    for r in sorted(rows, key=lambda x: (x["ts_code"], day(x["trade_date"]))):
        symbol = r["ts_code"]
        d = day(r["trade_date"])
        value = number(r["adj_factor"])
        if value <= 0 or (symbol, d) in seen:
            raise ValueError("invalid/duplicate cumulative factor")
        seen.add((symbol, d))
        prior = previous.get(symbol)
        if prior is not None and d <= prior[0]:
            raise ValueError("factor dates not advancing")
        if (
            prior is not None
            and d >= start
            and not math.isclose(value / prior[1], 1, rel_tol=1e-8)
        ):
            result.append(
                {"symbol": symbol, "trade_date": d, "ex_factor": value / prior[1]}
            )
        previous[symbol] = (d, value)
    return result


def realtime(rows, *, require_timestamp=False):
    result = []
    for r in rows:
        close = number(r["close"])
        prev = number(r["pre_close"])
        if close <= 0 or prev <= 0:
            continue
        timestamp = None
        if r.get("trade_time"):
            from zoneinfo import ZoneInfo

            dt = datetime.fromisoformat(r["trade_time"])
            dt = (
                dt.astimezone(ZoneInfo("Asia/Shanghai"))
                if dt.tzinfo
                else dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            )
            timestamp = int(dt.timestamp() * 1000)
        if timestamp is None and require_timestamp:
            log.warning(
                "Excluded undated RT snapshot; cannot safely assign a trading day"
            )
            continue
        result.append(
            {
                "symbol": r["ts_code"],
                "name": r.get("name"),
                "last_price": close,
                "prev_close": prev,
                **{k: number(r[k]) for k in ("open", "high", "low")},
                "volume": number(r["vol"]) / 100,
                "amount": number(r["amount"]),
                "change_pct": close / prev - 1,
                "change_amount": close - prev,
                "amplitude": (number(r["high"]) - number(r["low"])) / prev,
                "turnover_rate": None,
                "timestamp": timestamp,
            }
        )
    return result
