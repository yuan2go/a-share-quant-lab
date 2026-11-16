"""Initial command-line entrypoint. Intentionally no trade or data-sync actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .artifacts import read_prediction_batch
from .contracts import ArtifactValidationError
from .qlib_probe import probe_local_qlib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aql", description="A-share research lab (bootstrap)")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show implemented readiness, not research qualification")

    validate = commands.add_parser("validate-artifact", help="Validate one research prediction JSON")
    validate.add_argument("path", type=Path)

    probe = commands.add_parser("probe-qlib", help="Query already installed local Qlib daily data")
    probe.add_argument("--provider-uri", type=Path, required=True)
    probe.add_argument("--instrument", required=True, help="Qlib symbol, e.g. SH600519")
    probe.add_argument("--start", required=True, help="YYYY-MM-DD")
    probe.add_argument("--end", required=True, help="YYYY-MM-DD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = {
                "package": "a-share-quant-lab",
                "version": __version__,
                "stage": "bootstrap",
                "implemented": ["local-qlib-data-probe", "prediction-artifact-schema-validation"],
                "not_implemented": [
                    "market-data-ingestion",
                    "model-training",
                    "trade-signals",
                    "backtesting",
                    "tsp-integration",
                    "live-trading",
                ],
            }
        elif args.command == "validate-artifact":
            batch = read_prediction_batch(args.path)
            result = {
                "valid_schema": True,
                "run_id": batch["run_id"],
                "candidate_count": len(batch["predictions"]),
                "note": "Schema validity does not establish historical PIT or predictive value.",
            }
        else:
            result = probe_local_qlib(
                provider_uri=args.provider_uri,
                instrument=args.instrument,
                start=args.start,
                end=args.end,
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"aql: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
