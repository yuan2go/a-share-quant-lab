"""Opt-in, local-data-only smoke test for an installed Qlib provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def probe_local_qlib(
    provider_uri: Path,
    instrument: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Read one local Qlib close series. No model, download, or order is run."""
    if not provider_uri.is_dir():
        raise ValueError(f"Qlib data directory does not exist: {provider_uri}")
    if start > end:
        raise ValueError("start must be on or before end")
    if not instrument or not instrument.strip():
        raise ValueError("instrument must be specified in Qlib's own symbol format")

    try:
        import qlib
        from qlib.constant import REG_CN
        from qlib.data import D
    except ImportError as exc:
        raise RuntimeError("Qlib is not available; install in an isolated research environment") from exc

    qlib.init(provider_uri=str(provider_uri.resolve()), region=REG_CN)
    data = D.features(
        instruments=[instrument],
        fields=["$close"],
        start_time=start,
        end_time=end,
    )
    if data is None or data.empty:
        raise ValueError("Qlib returned no local close data for the requested instrument/range")
    return {
        "status": "local-data-readable",
        "instrument": instrument,
        "rows": len(data),
        "start": start,
        "end": end,
        "note": "Data read only; this is not a prediction, PIT qualification, or backtest.",
    }
