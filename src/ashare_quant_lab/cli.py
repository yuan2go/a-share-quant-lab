"""Research CLI: local DuckDB owner, Parquet study snapshots, no trading."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .artifacts import read_prediction_batch
from .qlib_probe import probe_local_qlib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aql", description="A-share quantitative research only")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Report implemented code versus real-data qualification")

    validate = commands.add_parser("validate-artifact", help="Check prediction JSON structure only")
    validate.add_argument("path", type=Path)

    probe = commands.add_parser("probe-qlib", help="Read existing Qlib data without training")
    probe.add_argument("--provider-uri", type=Path, required=True)
    probe.add_argument("--instrument", required=True)
    probe.add_argument("--start", required=True)
    probe.add_argument("--end", required=True)

    source = commands.add_parser("check-source", help="Live Tushare three-API coverage and unit probe")
    source.add_argument("--start", default="20261001")
    source.add_argument("--end", default="20261116")

    status = commands.add_parser("market-status", help="Read complete/failed market data captures")
    status.add_argument("--db-path", type=Path, default=Path("data/market.duckdb"))

    ingest = commands.add_parser("ingest-market", help="Fetch Tushare into a new versioned DuckDB capture")
    ingest.add_argument("--db-path", type=Path, default=Path("data/market.duckdb"))
    ingest.add_argument("--symbols-file", type=Path, required=True)
    ingest.add_argument("--start", required=True)
    ingest.add_argument("--end", required=True)
    ingest.add_argument("--pace-seconds", type=float, default=1.0)

    export = commands.add_parser("export-qlib-parquet", help="Immutable Parquet from completed DuckDB captures")
    export.add_argument("--db-path", type=Path, default=Path("data/market.duckdb"))
    export.add_argument("--symbols-file", type=Path, required=True)
    export.add_argument("--start", required=True)
    export.add_argument("--end", required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--capture-id", help="Pin a complete full-range capture; default latest eligible")
    export.add_argument("--min-history", type=int, default=60)

    convert = commands.add_parser("dump-qlib", help="Convert immutable Parquet using Qlib's official dump_bin.py")
    convert.add_argument("--qlib-repo", type=Path, required=True)
    convert.add_argument("--snapshot-dir", type=Path, required=True)
    convert.add_argument("--provider-uri", type=Path, required=True)

    study = commands.add_parser("run-first-study", help="Qlib Alpha158 vs momentum: retrospective RankIC")
    study.add_argument("--provider-uri", type=Path, required=True)
    study.add_argument("--manifest", type=Path, required=True)
    study.add_argument("--config", type=Path, required=True)
    study.add_argument("--output-dir", type=Path, required=True)

    direction = commands.add_parser("run-direction-study", help="Frozen monthly Qlib binary vs B0/B1")
    direction.add_argument("--provider-uri", type=Path, required=True)
    direction.add_argument("--manifest", type=Path, required=True)
    direction.add_argument("--config", type=Path, default=Path("configs/direction-study.json"))
    direction.add_argument("--output-dir", type=Path, required=True)

    latest = commands.add_parser("train-direction-latest", help="Frozen schedule latest-month Qlib training")
    latest.add_argument("--provider-uri", type=Path, required=True)
    latest.add_argument("--manifest", type=Path, required=True)
    latest.add_argument("--config", type=Path, default=Path("configs/direction-study.json"))
    latest.add_argument("--output-dir", type=Path, required=True)

    inference = commands.add_parser("infer-direction", help="Label-free latest direction probabilities")
    inference.add_argument("--provider-uri", type=Path, required=True)
    inference.add_argument("--manifest", type=Path, required=True)
    inference.add_argument("--model-dir", type=Path, required=True)
    inference.add_argument("--model-record-sha256", required=True, help="Explicit trusted model record hash")
    inference.add_argument("--calendar-clock", type=Path, required=True)
    inference.add_argument("--output", type=Path, required=True)

    review = commands.add_parser("review-direction", help="Append maturity labels; preserve original predictions")
    review.add_argument("--prediction", type=Path, required=True)
    review.add_argument("--provider-uri", type=Path, required=True)
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)

    inference.add_argument('--backfill', action='store_true', help='Flag replay or reconstructed publication')
    forward = commands.add_parser('summarize-direction', help='Pair retained issuances and immutable reviews')
    forward.add_argument('--prediction', type=Path, action='append', required=True)
    forward.add_argument('--review', type=Path, action='append', default=[])
    forward.add_argument('--output', type=Path, required=True)
    display = commands.add_parser('publish-direction-tsp', help='Publish a private direction page snapshot')
    display.add_argument('--summary', type=Path, required=True)
    display.add_argument('--tsp-data-dir', type=Path, required=True)
    publish = commands.add_parser("publish-tsp", help="Publish validated study outputs to a local TSP data directory")
    publish.add_argument("--study-dir", type=Path, required=True)
    publish.add_argument("--tsp-data-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = {
                "package": "a-share-quant-lab", "version": __version__,
                "stage": "retrospective-research-runner",
                "local_run_checked": False,
                "evidence_document": "docs/WP-AQL-FIRST-REAL-RESEARCH-01-RESULTS.md",
                "implemented_code": [
                    "tushare-duckdb-capture", "immutable-parquet-snapshot",
                    "official-qlib-binary-conversion", "qlib-ranking-study-runner", "qlib-direction-study-runner",
                    "label-free-direction-inference", "append-only-direction-review",
                    "duckdb-backed-tsp-historical-gateway", "tsp-research-page",
                ],
                "not_verified": [
                    "historical-PIT", "independent-OOS",
                    "tsp-mounted-page", "trading-returns",
                ],
                "live_trading": "NOT_SUPPORTED",
            }
        elif args.command == "validate-artifact":
            batch = read_prediction_batch(args.path)
            result = {
                "valid_schema": True, "run_id": batch["run_id"],
                "candidate_count": len(batch["predictions"]), "economic_claim": "NONE",
            }
        elif args.command == "probe-qlib":
            result = probe_local_qlib(
                provider_uri=args.provider_uri, instrument=args.instrument,
                start=args.start, end=args.end,
            )
        elif args.command == "check-source":
            from .source_audit import audit_source
            from .tushare_source import parse_day
            result = audit_source(parse_day(args.start), parse_day(args.end))
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["status"] == "RECEIVED_AND_DIMENSIONALLY_VALIDATED_NOT_PIT" else 2
        elif args.command == "market-status":
            from .market_store import latest_capture_status
            result = latest_capture_status(args.db_path)
        elif args.command == "ingest-market":
            from .market_ingest import ingest_market
            from .symbols import load_symbols
            from .tushare_source import TushareClient, parse_day
            result = ingest_market(
                args.db_path, TushareClient(), load_symbols(args.symbols_file),
                parse_day(args.start), parse_day(args.end),
                pace_seconds=args.pace_seconds,
            )
        elif args.command == "export-qlib-parquet":
            from .market_export import export_market_parquet
            from .symbols import load_symbols
            from .tushare_source import parse_day
            result = export_market_parquet(
                args.db_path, load_symbols(args.symbols_file),
                parse_day(args.start), parse_day(args.end), args.output_dir,
                min_history=args.min_history, capture_id=args.capture_id,
            )
        elif args.command == "dump-qlib":
            from .qlib_dump import dump_parquet_using_official_qlib
            result = dump_parquet_using_official_qlib(
                args.qlib_repo, args.snapshot_dir, args.provider_uri,
            )
        elif args.command == "run-first-study":
            from .first_study import run_first_qlib_study
            result = run_first_qlib_study(
                args.provider_uri, args.manifest, args.config, args.output_dir,
            )
        elif args.command == "run-direction-study":
            from .direction_study import run_direction_study
            result = run_direction_study(args.provider_uri, args.manifest, args.config, args.output_dir)
        elif args.command == "train-direction-latest":
            from .direction_study import train_latest
            result = train_latest(args.provider_uri, args.manifest, args.config, args.output_dir)
        elif args.command == "infer-direction":
            from .direction_inference import infer_direction
            result = infer_direction(args.provider_uri, args.manifest, args.model_dir,
                                     args.model_record_sha256, args.calendar_clock, args.output, backfill=args.backfill)
        elif args.command == "review-direction":
            from .direction_inference import review_direction
            result = review_direction(args.prediction, args.provider_uri, args.manifest, args.output)
        elif args.command == 'summarize-direction':
            from .direction_forward import summarize
            result = summarize(args.prediction,args.review,args.output)
        elif args.command == 'publish-direction-tsp':
            from .tsp_publish import publish_direction
            result = publish_direction(args.summary,args.tsp_data_dir)
        elif args.command == "publish-tsp":
            from .tsp_publish import publish_to_tsp
            result = publish_to_tsp(args.study_dir, args.tsp_data_dir)
        else:
            raise RuntimeError("unsupported command")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"aql: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
