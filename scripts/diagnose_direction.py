"""Audit the frozen 33 updates and decompose date-equal squared forecast error."""

import argparse
import json
from pathlib import Path

import pandas as pd

from ashare_quant_lab.direction_data import digest, direction_labels, initialize, load_native, write_json


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError(f"identity mismatch: {path.name}")


def diagnose(history, study, output):
    public = json.loads(Path("docs/research/direction-forecast-20261117-summary.json").read_text())
    verify(study / "study-report.json", public["historical_report_sha256"])
    report = json.loads((study / "study-report.json").read_text())
    manifest = history / "parquet/manifest.json"
    verify(manifest, report["snapshot_id"])
    data, _ = initialize(history / "binary", manifest, output.parent / "diagnostic-cache")
    cal, _, eligible, _, returns, _, _ = load_native(data, with_labels=True)
    labels = direction_labels(returns[eligible]).dropna()
    verify(study / "observations.parquet", report["observations_sha256"])
    verify(study / "daily-loss.parquet", report["daily_loss_sha256"])
    obs = pd.read_parquet(study / "observations.parquet")
    daily = pd.read_parquet(study / "daily-loss.parquet")
    months = {}
    for period, losses in daily.groupby(daily.index.to_period("M")):
        directory = study / "models" / str(period)
        record = json.loads((directory / "model-record.json").read_text())
        verify(directory / "model.txt", record["model_sha256"])
        rows = obs.loc[losses.index.min() : losses.index.max()]
        if set(rows.model_id) != {record["model_sha256"]} or record["snapshot_id"] != report["snapshot_id"]:
            raise ValueError("monthly identity mismatch")
        paired = rows.dropna(subset=["model", "raw", "b0", "b1", "y"])
        split = record["split"]
        stages = {}
        for name in ("train", "valid", "calibration"):
            start, end = split[name]
            y = labels.loc[start:end]
            if len(y) != record[name + "_pairs"]:
                raise ValueError("stage coverage mismatch")
            stages[name] = dict(dates=y.index.get_level_values(0).nunique(), pairs=len(y), up=y.mean())
        stages["evaluation"] = dict(dates=len(losses), pairs=len(paired), up=paired.y.mean())
        decomposition = {}
        for name in ("raw", "model", "b0", "b1"):
            error = paired[name] - paired.y
            means = error.groupby(level=0)
            common = means.mean().pow(2).mean()
            within = (error - means.transform("mean")).pow(2).groupby(level=0).mean().mean()
            decomposition[name] = dict(common=common, within=within)
        months[str(period)] = dict(
            split=split,
            stages=stages,
            expected=len(rows),
            excluded=len(rows) - len(paired),
            model_record_sha256=digest(directory / "model-record.json"),
            iteration=record["best_iteration"],
            calibrator=record["calibrator"],
            log_loss=losses.mean().to_dict(),
            raw_minus_b0=(losses.raw - losses.b0).mean(),
            raw_minus_b1=(losses.raw - losses.b1).mean(),
            model_minus_raw=(losses.model - losses.raw).mean(),
            probability_quantiles=paired[["model", "raw", "b0", "b1"]]
            .quantile([0.05, 0.5, 0.95])
            .to_dict(),
            brier_components=decomposition,
        )
    write_json(
        output,
        dict(
            snapshot=report["snapshot_id"],
            original_report=public["historical_report_sha256"],
            months=months,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "study", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    diagnose(args.history, args.study, args.output)
