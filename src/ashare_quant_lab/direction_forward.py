"""Summarize a supplied immutable issuance and review history for one experiment."""

from collections import defaultdict
from datetime import datetime, time
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from .direction_data import EVENT, digest, write_json
from .direction_evaluation import probability_metrics
from .symbols import load_symbols

CORE = ("calibrated", "raw", "b0", "b1")
SHANGHAI = ZoneInfo("Asia/Shanghai")
CONFIG = Path(__file__).resolve().parents[2] / "configs"


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timezone required")
    return stamp


def close(day):
    return datetime.combine(datetime.fromisoformat(day).date(), time(15), SHANGHAI)


def issuance(batch):
    if batch.get("publication_kind", "NATURAL") != "NATURAL":
        return "BACKFILL"
    if batch["status"] != "CURRENT_COMPLETED_SESSION_RESEARCH_ONLY":
        return batch["status"]
    interval = batch["prediction_interval"]
    if not interval["start_date"] or not interval["end_date"]:
        return "UNKNOWN_INTERVAL"
    issued = timestamp(batch["generated_at"])
    if not batch["data_through"] < interval["start_date"] < interval["end_date"]:
        return "INVALID_TARGET_INTERVAL"
    if issued >= close(interval["start_date"]):
        return "DELAYED_AFTER_TARGET_ENTRY_CLOSE"
    if batch.get("data_kind") != "REAL_SOURCE_RETROSPECTIVE":
        return "UNVERIFIED_SOURCE"
    if batch.get("source_capture_started_at") and timestamp(batch["source_capture_started_at"]) < close(
        batch["data_through"]
    ):
        return "UNVERIFIED_SIGNAL_CLOSE"
    if (
        issued < close(batch["data_through"])
        or not batch.get("snapshot_exported_at")
        or timestamp(batch["snapshot_exported_at"]) > issued
        or batch["expected_latest_completed_session"] != batch["data_through"]
        or batch["training_split"]["anchor"][:7] != batch["data_through"][:7]
        or batch["training_split"]["mature_through"] >= batch["data_through"]
    ):
        return "INVALID_INFORMATION_CLOCK"
    if batch.get("issuance_status") != "ISSUED_BEFORE_TARGET_ENTRY_CLOSE":
        return batch.get("issuance_status", "UNKNOWN_ISSUANCE")
    rows = batch["predictions"]
    if sorted(p["symbol"] for p in rows) != load_symbols(CONFIG / "first-study-cohort.txt"):
        return "INCOMPLETE_COHORT"
    required = CORE + (("recent",) if batch.get("recent_baseline_applicable") else ())
    for row in rows:
        if row["data_quality"] != "FULL_RAW_LOOKBACK":
            return "INCOMPLETE_COHORT"
        for name in required:
            value = row.get(name + "_probability")
            if value is None or not math.isfinite(value) or not 0 <= value <= 1:
                return "INCOMPLETE_PROBABILITIES"
    return "ELIGIBLE_ISSUANCE"


def read_records(paths):
    return {digest(p): json.loads(Path(p).read_text()) for p in paths}


def summarize(predictions, reviews, output):
    import pandas as pd

    batches = read_records(predictions)
    if len({b["work_package"] for b in batches.values()}) != 1 or any(
        b.get("kind") != "DIRECTION_PREDICTION" or b["up_event"] != EVENT for b in batches.values()
    ):
        raise ValueError("supply one experiment and target per summary")
    linked = defaultdict(list)
    for sha, review in read_records(reviews).items():
        batch = batches.get(review["prediction_sha256"])
        if (
            not batch
            or review["kind"] != "DIRECTION_MATURITY_REVIEW"
            or review["model_id"] != batch["model_id"]
            or review["original_inference_snapshot_id"] != batch["inference_snapshot_id"]
        ):
            raise ValueError("unbound maturity review")
        linked[review["prediction_sha256"]].append((sha, review))
    rows, audit, selected, seen = [], [], set(), set()
    latest = None
    for sha, batch in sorted(
        batches.items(), key=lambda item: (timestamp(item[1]["generated_at"]), item[0])
    ):
        day = batch["data_through"]
        qualification = issuance(batch)
        duplicate = day in seen
        seen.add(day)
        primary_issuance = qualification == "ELIGIBLE_ISSUANCE" and day not in selected
        if primary_issuance:
            selected.add(day)
        history = sorted(linked[sha], key=lambda pair: (timestamp(pair[1]["reviewed_at"]), pair[0]))

        # Revisions remain visible. Freeze the earliest source-qualified post-close
        # review, even when some endpoint labels are missing.
        def verified(pair):
            r = pair[1]
            end = batch["prediction_interval"]["end_date"]
            start = r.get("review_capture_started_at")
            finish = r.get("review_capture_completed_at")
            return (
                r["status"] in ("MATURE_REVIEW", "PARTIAL_MISSING_LABELS")
                and end
                and r["data_through"] >= end
                and r.get("review_data_kind") == "REAL_SOURCE_RETROSPECTIVE"
                and start
                and finish
                and close(end) <= timestamp(start) <= timestamp(finish) <= timestamp(r["reviewed_at"])
            )

        primary = next((pair for pair in history if verified(pair)), history[-1] if history else (None, {}))
        review_sha, review = primary
        status = review.get("status", "UNREVIEWED")
        if status in ("MATURE_REVIEW", "PARTIAL_MISSING_LABELS") and not verified(primary):
            status = "UNVERIFIED_MATURITY_SOURCE"
        audit.append(
            dict(
                date=day,
                prediction_sha256=sha,
                issuance=qualification,
                primary_issuance=primary_issuance,
                reissue=duplicate,
                maturity=status,
                primary_review=review_sha,
                supplied_reviews=[p[0] for p in history],
            )
        )
        labels = {r["symbol"]: r for r in review.get("labels", [])}
        if review and (
            len(labels) != len(review["labels"])
            or set(labels) != {p["symbol"] for p in batch["predictions"]}
        ):
            raise ValueError("review security keys differ from issuance")
        if status == "MATURE_REVIEW" and primary_issuance:
            for p in batch["predictions"]:
                label = labels[p["symbol"]]
                if (
                    label["y"] not in (0, 1)
                    or not math.isfinite(label["return"])
                    or label["y"] != (label["return"] > 0)
                ):
                    raise ValueError("invalid mature label")
                rows.append(
                    dict(
                        datetime=day,
                        instrument=p["symbol"],
                        y=label["y"],
                        **{"return": label["return"]},
                        **{n: p.get(n + "_probability") for n in (*CORE, "recent")},
                    )
                )
        view = {
            k: batch.get(k)
            for k in (
                "work_package",
                "generated_at",
                "data_through",
                "model_id",
                "model_record_sha256",
                "inference_snapshot_id",
                "training_snapshot_id",
                "prediction_interval",
                "status",
                "issuance_status",
                "calibration_status",
                "predictions",
            )
        }
        view["data_status"] = (
            "CURRENT_AT_ISSUE"
            if batch["data_through"] == batch["expected_latest_completed_session"]
            else "SESSION_MISMATCH"
        )
        view["model_status"] = (
            "CURRENT_MONTH_AT_ISSUE" if batch["training_split"]["anchor"][:7] == day[:7] else "STALE_MONTH"
        )
        view.update(
            qualification=qualification,
            reissue=duplicate,
            maturity=status,
            labels=list(labels.values()),
            prediction_sha256=sha,
        )
        if latest is None or (day, qualification == "ELIGIBLE_ISSUANCE") > (
            latest["data_through"],
            latest["qualification"] == "ELIGIBLE_ISSUANCE",
        ):
            latest = view
    paired = {}
    frame = pd.DataFrame(
        rows, columns=["datetime", "instrument", "y", "return", *CORE, "recent"]
    ).set_index(["datetime", "instrument"])
    for key, methods in [("original_methods", CORE), ("including_recent", (*CORE, "recent"))]:
        common = frame.dropna(subset=list(methods))
        metrics = {n: probability_metrics(common, n) for n in methods}
        paired[key] = dict(
            pairs=len(common),
            dates=common.index.get_level_values(0).nunique(),
            metrics=metrics,
            calibrated_minus={
                n: {
                    m: metrics["calibrated"][m] - metrics[n][m] if len(common) else None
                    for m in ("brier", "log_loss")
                }
                for n in methods
                if n != "calibrated"
            },
        )
    write_json(output, dict(kind="DIRECTION_FORWARD_SUMMARY", latest=latest, batches=audit, paired=paired))
    return dict(summary=str(output), batches=len(audit), pairs=paired["original_methods"]["pairs"])
