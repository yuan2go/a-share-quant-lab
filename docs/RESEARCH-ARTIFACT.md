# Prediction artifact contract — V1

Status: IMPLEMENTED STRUCTURE ONLY. Validating JSON does **not** verify historical PIT availability, that a Qlib model ran, or that its scores are predictive.

A producer (future Qlib experiment adapter) publishes an immutable, versioned prediction batch. A TSP reader may only display it as research, not as trade authorization.

## Required JSON fields

| Key | Semantics |
| --- | --- |
| schema_version | Integer 1 |
| run_id | Immutable unique experiment/result identity supplied by producer |
| created_at | Result creation timestamp, offset-aware ISO-8601 |
| signal_cutoff | Latest information cutoff used to form the signal, offset-aware ISO-8601 |
| market | Fixed value CN-A |
| forecast_horizon_days | Positive integer number of trading days, not calendar days |
| model_id | Exact model/config identity (name alone is insufficient for future adoption) |
| universe_id | Versioned dynamic eligible-universe identity |
| data_snapshot_id | Version/hash reference for the input dataset, which still requires independent provenance checks |
| predictions | Array of unique { symbol, score }; symbols in NNNNNN.SH or NNNNNN.SZ format; finite numeric scores. Empty means no output candidates and is valid. |

An **illustrative schema-only payload** (not a real model output) is:

\`\`\`json
{
  "schema_version": 1,
  "run_id": "example-only-no-model-executed",
  "created_at": "2026-11-16T16:00:00+08:00",
  "signal_cutoff": "2026-11-16T15:05:00+08:00",
  "market": "CN-A",
  "forecast_horizon_days": 10,
  "model_id": "example-untrained",
  "universe_id": "example-not-PIT-qualified",
  "data_snapshot_id": "example-no-real-data",
  "predictions": []
}
\`\`\`

\`aql validate-artifact FILE\` checks structure, valid timestamps, allowed symbol format, finite scores and duplicate symbols. It cannot establish that underlying information was actually available at cutoff. Actual capture/publish/revision history, coverage, training identity, output artifacts and integrity hashes are future producer responsibilities.

A score is an arbitrary model output, **not an implied probability of winning, predicted percent return, signal to buy, or realized performance**. Buy/sell eligibility, positions, fills and net P&L belong to separate, future versioned contracts.

A research interface should explicitly distinguish no candidates, unavailable/stale data, unvalidated score, failed study, and no trade.
