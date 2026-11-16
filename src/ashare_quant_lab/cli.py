"""Research CLI. Live trading intentionally unsupported."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from . import __version__
from .artifacts import read_prediction_batch
from .qlib_probe import probe_local_qlib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aql", description="A-share research lab (research-only)")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show research capability and verification boundaries")

    validate = commands.add_parser("validate-artifact", help="Validate prediction JSON structure only")
    validate.add_argument("path", type=Path)

    probe = commands.add_parser("probe-qlib", help="Read local Qlib data without training")
    probe.add_argument("--provider-uri", type=Path, required=True)
    probe.add_argument("--instrument", required=True)
    probe.add_argument("--start", required=True)
    probe.add_argument("--end", required=True)

    source = commands.add_parser("check-source", help="Read-only Tushare HTTP trade-calendar probe")
    source.add_argument("--start", default="20261001")
    source.add_argument("--end", default="20261116")

    export = commands.add_parser("export-qlib-csv", help="Fetch adjusted CSV research snapshot via Tushare")
    export.add_argument("--symbols-file", required=True, type=Path)
    export.add_argument("--start", required=True)
    export.add_argument("--end", required=True)
    export.add_argument("--output-dir", required=True, type=Path)
    export.add_argument("--pace-seconds", type=float, default=1.0)

    convert = commands.add_parser("dump-qlib", help="Run official Qlib dump_bin.py from a source checkout")
    convert.add_argument("--qlib-repo", required=True, type=Path)
    convert.add_argument("--csv-dir", required=True, type=Path)
    convert.add_argument("--provider-uri", required=True, type=Path)

    study = commands.add_parser("run-first-study", help="Qlib Alpha158 + LightGBM versus momentum RankIC")
    study.add_argument("--provider-uri", required=True, type=Path)
    study.add_argument("--manifest", required=True, type=Path)
    study.add_argument("--config", required=True, type=Path)
    study.add_argument("--output-dir", required=True, type=Path)

    publish = commands.add_parser("publish-tsp", help="Copy existing study output into local TSP data directory")
    publish.add_argument("--study-dir", required=True, type=Path)
    publish.add_argument("--tsp-data-dir", required=True, type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = {
                "package": "a-share-quant-lab", "version": __version__,
                "stage": "adapter-implementation_not_live_validated",
                "implemented_code": ["tushare-daily-gateway", "event-factor-conversion", "csv-export", "qlib-selection-runner", "tsp-extension-package"],
                "not_verified": ["tushare-gateway-connectivity", "historical-PIT", "qlib-model-execution", "tsp-mounted-page", "trading-returns"],
                "live_trading": "NOT_SUPPORTED",
            }
        elif args.command == "validate-artifact":
            batch = read_prediction_batch(args.path)
            result = {"valid_schema": True, "run_id": batch["run_id"], "candidate_count": len(batch["predictions"]), "economic_claim": "NONE"}
        elif args.command == "probe-qlib":
            result = probe_local_qlib(provider_uri=args.provider_uri, instrument=args.instrument, start=args.start, end=args.end)
        elif args.command == "check-source":
            from .tushare_source import TushareClient
            rows = TushareClient().query("trade_cal", exchange="SSE", start_date=args.start, end_date=args.end)
            result = {"source": "tushare-http", "api": "trade_cal", "rows": len(rows), "sample_dates": [str(r.get("cal_date")) for r in rows[:3]], "dataset_qualified": False}
        elif args.command == "export-qlib-csv":
            from .qlib_export import export_qlib_csv, load_symbols
            from .tushare_source import TushareClient, parse_day
            result = export_qlib_csv(
                TushareClient(), load_symbols(args.symbols_file),
                parse_day(args.start), parse_day(args.end),
                args.output_dir, pace_seconds=args.pace_seconds,
            )
        elif args.command == "dump-qlib":
            from .qlib_dump import dump_csv_using_official_qlib
            result = dump_csv_using_official_qlib(args.qlib_repo, args.csv_dir, args.provider_uri)
        elif args.command == "run-first-study":
            from .first_study import run_first_qlib_study
            result = run_first_qlib_study(args.provider_uri, args.manifest, args.config, args.output_dir)
        elif args.command == "publish-tsp":
            from .tsp_publish import publish_to_tsp
            result = publish_to_tsp(args.study_dir, args.tsp_data_dir)
        else:
            raise RuntimeError("unsupported command")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"aql: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
