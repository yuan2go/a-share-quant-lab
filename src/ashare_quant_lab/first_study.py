"""Qlib Alpha158+LightGBM versus simple momentum: retrospective ranking study.

No portfolio execution and no economic alpha claims. This is a research entry,
not a permanent automated prediction or market-wide trade recommendation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime, date, timezone
from pathlib import Path

from .contracts import validate_prediction_batch
from .symbols import qlib_to_symbol
from .research_evaluation import StudyError, canonical_series, paired_rank_ic


def validate_study_config(config: dict, dates: list[date] | None = None) -> dict:
    keys = {"train", "valid", "test", "horizon", "min_cross_section"}
    if not isinstance(config, dict) or set(config) != keys:
        raise StudyError(f"config must have exactly: {sorted(keys)}")
    if config["horizon"] != 10 or type(config["horizon"]) is not int:
        raise StudyError("first experiment uses the predeclared 10-session label")
    n = config["min_cross_section"]
    if type(n) is not int or n < 5:
        raise StudyError("min_cross_section must be >= 5")
    parsed = {}
    for k in ("train", "valid", "test"):
        values = config[k]
        if not isinstance(values, list) or len(values) != 2:
            raise StudyError(f"{k} must have [start, end]")
        try:
            parsed[k] = (date.fromisoformat(values[0]), date.fromisoformat(values[1]))
        except (TypeError, ValueError) as exc:
            raise StudyError(f"{k} contains invalid dates") from exc
        if parsed[k][0] > parsed[k][1]:
            raise StudyError(f"{k} reversed")
    if not (parsed["train"][1] < parsed["valid"][0] and parsed["valid"][1] < parsed["test"][0]):
        raise StudyError("training/validation/test must be strictly time ordered")
    if dates is not None:
        cal = sorted(set(dates))
        for left, right in (("train", "valid"), ("valid", "test")):
            gap = sum(parsed[left][1] < d < parsed[right][0] for d in cal)
            if gap < 11:
                raise StudyError(f"forward-label embargo too short between {left} and {right}: {gap} sessions")
        after_test = sum(d > parsed["test"][1] for d in cal)
        if after_test < 11:
            raise StudyError(f"not enough market data to mature 10-session test labels: {after_test}")
    return config


def run_first_qlib_study(
    provider_uri: Path, manifest_path: Path, config_path: Path, output_dir: Path
) -> dict:
    """Execute Qlib in an isolated ML environment with local, already dumped data."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("point_in_time_status") != "RETROSPECTIVE_ONLY":
        raise StudyError("unexpected source/PIT declaration")
    snapshot_id = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    config_bytes = config_path.read_bytes()
    config = validate_study_config(json.loads(config_bytes))
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError("experiment output exists; refusing overwrite")
    if not provider_uri.is_dir():
        raise StudyError("Qlib provider path does not exist")
    lineage_path = provider_uri / "aql_source_manifest.json"
    if not lineage_path.is_file():
        raise StudyError("Qlib provider has no source lineage record; run official dump wrapper")
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    if lineage.get("source_manifest_sha256") != snapshot_id:
        raise StudyError("Qlib provider and source snapshot IDs disagree")
    try:
        import pandas as pd
        import qlib
        from qlib.constant import REG_CN
        from qlib.contrib.data.handler import Alpha158
        from qlib.contrib.model.gbdt import LGBModel
        from qlib.data import D
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.workflow import R
    except ImportError as exc:
        raise StudyError("Qlib/LightGBM/pandas unavailable in this environment") from exc

    from .qlib_dump import verify_binary_identity
    verify_binary_identity(provider_uri)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    recorder_dir = output_dir.parent / ('.' + output_dir.name + '-mlruns')
    qlib.init(provider_uri=str(provider_uri.resolve()), region=REG_CN,
              kernels=4, joblib_backend="threading",
              local_cache_path=str(output_dir.parent / ("." + output_dir.name + "-cache")),
              exp_manager={"class": "MLflowExpManager", "module_path": "qlib.workflow.expm",
                           "kwargs": {"uri": str(recorder_dir), "default_exp_name": "aql"}})
    cal = list(D.calendar(start_time=config["train"][0], end_time=None, freq="day"))
    all_dates = [pd.Timestamp(d).date() for d in cal]
    validate_study_config(config, all_dates)
    # Do not invent an OOS credential or a time-available universe from current listings.
    if not manifest.get("universe"):
        raise StudyError("missing universe")
    # Dump_bin's all.txt must match the exact study cohort. Refuse extra securities.
    available = D.instruments(market="all")
    codes = D.list_instruments(available, start_time=config["train"][0], end_time=config["test"][1], as_list=True)
    expected = {s.split(".")[1] + s.split(".")[0] for s in manifest["universe"]}
    if set(str(c).upper() for c in codes) != expected:
        raise StudyError("Qlib instrument list differs from snapshot cohort; no silent universe enlargement")
    fit_start, fit_end = config["train"]
    handler = Alpha158(
        instruments="all",
        start_time=str(config["train"][0]),
        end_time=max(all_dates).isoformat(),
        fit_start_time=str(fit_start),
        fit_end_time=str(fit_end),
        # T-close signal. Label: T+1 close to T+11 close, 10 sessions of
        # holding; prediction label is not an executable fill simulation.
        label=(["Ref($close, -11)/Ref($close, -1) - 1"], ["LABEL0"]),
    )
    segments = {k: tuple(str(day) for day in v) for k, v in config.items() if k in ("train", "valid", "test")}
    dataset = DatasetH(handler=handler, segments=segments)
    target_audit = _verify_targets(dataset, D, all_dates)
    model = LGBModel(
        loss="mse",
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        num_threads=4,
        num_boost_round=240,
        early_stopping_rounds=30,
        seed=23,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aql-study-", dir=output_dir.parent))
    try:
        # LGBModel.fit logs training metrics through the official Qlib recorder.
        with R.start(experiment_name="aql_first_selection"):
            model.fit(dataset)
            prediction = model.predict(dataset, segment="test")
            model.model.save_model(str(stage / "model.txt"))
        label = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_R).iloc[:, 0]
        baseline = D.features(
            instruments=D.instruments("all"),
            fields=["$close/Ref($close, 20)-1"],
            start_time=config["test"][0],
            end_time=config["test"][1],
        ).iloc[:, 0]
        prediction = canonical_series(prediction, "model")
        baseline = canonical_series(baseline, "momentum")
        label = canonical_series(label, "label")
        paired, daily, observations = paired_rank_ic(
            prediction, baseline, label, config["min_cross_section"])
        observations.to_parquet(stage / "paired-observations.parquet")
        (stage / "daily-rank-ic.json").write_text(json.dumps(daily, indent=2, allow_nan=False) + "\n")
        ml_paired = {"mean_rank_ic": paired["model_mean_rank_ic"], "days": paired["days"], "pairs": paired["pairs"]}
        baseline_paired = {"mean_rank_ic": paired["momentum_mean_rank_ic"], "days": paired["days"], "pairs": paired["pairs"]}
        recent = prediction.dropna()
        recent_date = recent.index.get_level_values(0).max()
        recent = recent.loc[recent_date]
        predictions = [
            {"symbol": qlib_to_symbol(str(symbol).upper()), "score": float(score)}
            for symbol, score in recent.items() if math.isfinite(float(score))
        ]
        predictions.sort(key=lambda r: (-r["score"], r["symbol"]))
        cutoff = pd.Timestamp(recent_date).tz_localize("Asia/Shanghai") + pd.Timedelta(hours=18)
        created = datetime.now(timezone.utc)
        run_id = hashlib.sha256(config_bytes + snapshot_id.encode() + created.isoformat().encode()).hexdigest()[:24]
        payload = {
            "schema_version": 1, "run_id": run_id, "created_at": created.isoformat(),
            "signal_cutoff": cutoff.isoformat(), "market": "CN-A",
            "forecast_horizon_days": 10,
            "model_id": (
                f"qlib-{qlib.__version__}-lightgbm-alpha158-v1-"
                f"{hashlib.sha256(config_bytes + Path(__file__).read_bytes()).hexdigest()[:12]}"
            ),
            "universe_id": hashlib.sha256(",".join(manifest["universe"]).encode()).hexdigest(),
            "data_snapshot_id": snapshot_id,
            "predictions": predictions,
        }
        validate_prediction_batch(payload)
        (stage / "experiment-config.json").write_bytes(config_bytes)
        study = {
            "run_id": run_id, "status": "RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED",
            "universe_size": len(manifest["universe"]),
            "data_snapshot_id": snapshot_id,
            "label": "T+1 close to T+11 close adjusted-price relative return; not a fill",
            "test_segment": config["test"], "paired_evaluation": paired,
            "model_rank_ic_paired": ml_paired,
            "momentum_rank_ic_paired": baseline_paired,
            "paired_ic_difference": ml_paired["mean_rank_ic"] - baseline_paired["mean_rank_ic"],
            "model_sha256": hashlib.sha256((stage / "model.txt").read_bytes()).hexdigest(),
            "runtime": _runtime_identity(config_bytes, model, manifest, lineage, dataset),
            "target_audit": target_audit,
            "latest_prediction_date": str(recent_date)[:10],
            "predictive_probability": None, "economic_net_return": None, "trade_decision": "NOT_QUALIFIED",
            "disclaimer": "Fixed-cohort retrospective; no PIT proof, fees, order simulation, OOS qualification or economic alpha.",
        }
        (stage / "prediction-batch.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        (stage / "study-report.json").write_text(json.dumps(study, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        os.replace(stage, output_dir)
        return {"status": study["status"], "run_id": run_id, "output_dir": str(output_dir), "paired_ic_difference": study["paired_ic_difference"]}
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _runtime_identity(config_bytes, model, manifest, lineage, dataset):
    import importlib.metadata
    import platform
    import numpy as np
    import subprocess
    from qlib.data.dataset.handler import DataHandlerLP

    segments = {}
    for key in ("train", "valid", "test"):
        raw = dataset.prepare(key, col_set="label", data_key=DataHandlerLP.DK_R).iloc[:, 0]
        learn = dataset.prepare(key, col_set="label", data_key=DataHandlerLP.DK_L).iloc[:, 0]
        features = dataset.prepare(key, col_set="feature", data_key=DataHandlerLP.DK_I)
        finite_features = np.isfinite(features.to_numpy())
        segments[key] = {"feature_values": int(features.size),
                         "nonfinite_feature_values": int(features.size - finite_features.sum()),
                         "rows_without_any_finite_features": int((~finite_features.any(axis=1)).sum()),
                         "raw_rows": len(raw), "raw_finite_labels": int(canonical_series(raw, key).notna().sum()),
                         "learn_rows": len(learn), "first": str(raw.index.get_level_values("datetime").min()),
                         "last": str(raw.index.get_level_values("datetime").max())}
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return {"python": platform.python_version(),
            "packages": {p: importlib.metadata.version(p) for p in
                         ("pyqlib", "lightgbm", "pandas", "numpy", "duckdb", "pyarrow", "mlflow")},
            "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
            "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in Path(__file__).parent.glob("*.py")},
            "git_revision": revision.stdout.strip(),
            "alpha158_feature_count": dataset.prepare("train", col_set="feature", data_key=DataHandlerLP.DK_L).shape[1],
            "learn_label_transform": "Qlib default DropnaLabel + CSZScoreNorm; evaluation uses raw DK_R returns",
            "model_parameters": model.params, "num_boost_round": model.num_boost_round,
            "early_stopping_rounds": model.early_stopping_rounds,
            "best_iteration": model.model.best_iteration,
            "source_capture_ids": manifest.get("source_capture_ids"),
            "binary_lineage": lineage, "segments": segments,
            "information_cutoff": "Assumed T 18:00 after-close features; actual source capture is retrospective, not historical availability proof",
            "label_maturity": "11 source-calendar sessions required before following segment and after test"}


def _verify_targets(dataset, data, all_dates):
    """Audit native label expressions against independent calendar shifts."""
    import numpy as np
    import pandas as pd
    from qlib.data.dataset.handler import DataHandlerLP

    close = canonical_series(data.features(instruments=data.instruments("all"), fields=["$close"],
                             start_time=all_dates[0], end_time=all_dates[-1]).iloc[:, 0], "close")
    wide = close.unstack("instrument").reindex(pd.DatetimeIndex(all_dates))
    expected = wide.shift(-11) / wide.shift(-1) - 1
    momentum = canonical_series(data.features(instruments=data.instruments("all"),
                                fields=["$close/Ref($close, 20)-1"],
                                start_time=all_dates[0], end_time=all_dates[-1]).iloc[:, 0], "momentum")
    wanted_momentum = wide / wide.shift(20) - 1
    wanted_values = np.array([wanted_momentum.at[d, i] for d, i in momentum.index])
    if not np.allclose(momentum.to_numpy(), wanted_values, equal_nan=True, rtol=2e-5, atol=2e-7):
        raise StudyError("native momentum differs from 20-calendar-session return")
    audits = {"momentum": {"checked_rows": len(momentum), "status": "NATIVE_MOMENTUM_MATCHES_CALENDAR_SHIFT"}}
    for segment in ("train", "valid", "test"):
        label = canonical_series(dataset.prepare(segment, col_set="label", data_key=DataHandlerLP.DK_R).iloc[:, 0], "label")
        wanted = np.array([expected.at[d, i] for d, i in label.index])
        if not np.allclose(label.to_numpy(), wanted, equal_nan=True, rtol=2e-5, atol=2e-7):
            raise StudyError(f"native label differs from calendar-shift return: {segment}")
        audits[segment] = {"checked_rows": len(label), "finite_labels": int(label.notna().sum()),
                           "status": "NATIVE_LABEL_MATCHES_CALENDAR_SHIFT"}
    return audits
