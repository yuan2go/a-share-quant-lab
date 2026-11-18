"""Compare immutable original and refit studies on identical date/security keys."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ashare_quant_lab.direction_data import digest, write_json
from ashare_quant_lab.direction_evaluation import block_interval, probability_metrics


def compare(original, candidate, output):
    public = json.loads(Path("docs/research/direction-forecast-20261117-summary.json").read_text())
    if digest(original / "study-report.json") != public["historical_report_sha256"]:
        raise ValueError("original study report identity mismatch")
    reports, frames = [], []
    for directory, config in [(original, "direction-study"), (candidate, "direction-refit")]:
        report = json.loads((directory / "study-report.json").read_text())
        path = directory / "observations.parquet"
        if (
            digest(path) != report["observations_sha256"]
            or digest(Path("configs") / (config + ".json")) != report["config_sha256"]
            or report["snapshot_id"] != public["historical_snapshot_id"]
        ):
            raise ValueError("study input identity mismatch")
        reports.append(digest(directory / "study-report.json"))
        frames.append(pd.read_parquet(path))
    old, new = frames
    if not old[["y", "return", "b0", "b1", "reason"]].equals(new[["y", "return", "b0", "b1", "reason"]]):
        raise ValueError("cohort, labels, qualification or control probabilities differ")
    methods = ["model", "raw", "original", "original_raw", "b0", "b1", "recent"]
    rows = new.assign(original=old.model, original_raw=old.raw)
    common = rows.dropna(subset=["y", *methods])
    axis = rows.index.get_level_values("datetime").unique().sort_values()
    daily = {}
    for name in methods:
        p = common[name].clip(1e-6, 1 - 1e-6)
        loss = -(common.y * np.log(p) + (1 - common.y) * np.log1p(-p))
        daily[name] = loss.groupby(level="datetime").mean().reindex(axis)
    diffs = {}
    for name in ["original", "b0", "b1", "recent"]:
        diff = daily["model"] - daily[name]
        diffs[name] = dict(
            mean=diff.mean(),
            interval=block_interval(diff, block=20, replicates=2000, seed=23),
            years=diff.groupby(diff.index.year).mean().to_dict(),
        )
    conclusion = "NO_CONSISTENT_INCREMENT"
    if all(d["mean"] < 0 for d in diffs.values()):
        conclusion = "INSUFFICIENT_EVIDENCE"
        if all(
            d["interval"]["upper"] is not None
            and d["interval"]["upper"] < 0
            and max(d["years"].values()) < 0
            for d in diffs.values()
        ):
            conclusion = "LIMITED_RETROSPECTIVE_GAIN"
    write_json(
        output,
        dict(
            original_report=reports[0],
            candidate_report=reports[1],
            snapshot=public["historical_snapshot_id"],
            candidate_work_package="WP-AQL-DIRECTION-DIAGNOSIS-02",
            candidate_config_sha256=digest(Path("configs/direction-refit.json")),
            conclusion=conclusion,
            expected=len(rows),
            output_pairs={n: int(rows[n].count()) for n in methods},
            own={n: probability_metrics(rows.dropna(subset=["y", n]), n) for n in methods},
            common={n: probability_metrics(common, n) for n in methods},
            differences=diffs,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "candidate", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    compare(args.original, args.candidate, args.output)
