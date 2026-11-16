"""A-share identifier mapping for Qlib and the research/UI boundary."""
from __future__ import annotations

from pathlib import Path

from .tushare_source import validate_symbol


def symbol_to_qlib(symbol: str) -> str:
    validate_symbol(symbol)
    code, market = symbol.split(".")
    return market + code


def qlib_to_symbol(instrument: str) -> str:
    if not isinstance(instrument, str) or len(instrument) != 8:
        raise ValueError("invalid Qlib instrument")
    symbol = f"{instrument[2:]}.{instrument[:2].upper()}"
    return validate_symbol(symbol)


def load_symbols(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    symbols = [validate_symbol(line.split("#", 1)[0].strip()) for line in lines if line.split("#", 1)[0].strip()]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("cohort must contain unique, nonempty A-share symbols")
    return sorted(symbols)
