# Architecture and responsibility boundaries

Status: INITIAL DESIGN. Verified implementation is limited to the CLI, schema validator and local Qlib data probe.

## Components and ownership

1. **Data source & immutable snapshots (planned):** licensed A-share data from a permitted provider, historical listings/delistings, symbol mapping, availability times, corporate actions and trade restrictions. Qlib data ingestion will be a dedicated adapter, not page-side fetching.
2. **Qlib research process (planned):** Qlib factor/model tooling, chronological experiments, prediction batches and research backtests. Can run locally or as an isolated worker, never in the TSP HTTP request thread.
3. **A-Share Quant Lab (partially implemented):** user research definitions, explicit prediction-batch contract, point-in-time and quality qualifications, stock selection, buy/hold/sell/no-trade research and evidence review. Today only contract validation and local data-read smoke test exist.
4. **TSP (not yet integrated):** React dashboard and stock preview. Prefer an isolated TSP backend/frontend extension package using documented extension hooks and read-only results APIs; do not copy TSP core, make it a source of training truth, or install Qlib in its main web worker by default.
5. **MRA (out of scope):** existing independent execution/evidence research. A future integration may import versioned artifacts only after proving extra utility; it must not mutate its runtime or imply live-trading authorization.

        External historical data
                  |
          source snapshot + PIT
                  |
          Qlib experiments
                  |
        versioned research artifact
                  |
          read-only TSP adapter
                  |
          portfolio research UI

## One economic authority per comparison

Qlib and TSP each have backtesting facilities. A performance comparison must use **one audited execution/cost basis** with a common date range, source snapshot, dynamic universe, portfolio construction and feasible order rules. Displaying unrelated net-value curves side by side is not a valid comparative study.

A prediction result is not a trading instruction. The lab must explicitly translate forecast -> candidate -> eligibility -> target portfolio -> feasible orders -> fills -> net equity, recording any no-op, rejection and failed fill.

## Data and time

- Qlib symbols (for example SH600519) and market symbols (600519.SH) require an explicit, versioned mapping; this is not yet implemented.
- Raw execution prices and adjusted/total-return signals are not interchangeable; define corporate action accounting and cash dividend treatment before economic comparisons.
- Record event/effective time, public availability time, snapshot capture time, data revision, model version, training/test spans, signal cutoff and publication timestamp.
- Never use current security membership, status or financial revision as a proxy for an unavailable historical value.
- Research labels must be future values isolated from the feature/signal pipeline, with training–evaluation boundary protection.

## Interface direction

A V1 machine-readable prediction format is specified in [RESEARCH-ARTIFACT.md](RESEARCH-ARTIFACT.md). It represents numeric model ranking scores, not calibrated probabilities or executable recommendations.

Do not add a new persistence database, scheduler, LLM agent, duplicate backtest engine, browser implementation or brokerage interface during bootstrap without a demonstrated need.

### Upstream reference versions (not integrated or tested here)
- Microsoft Qlib upstream release v0.9.8 (2026-10-08); optional local Python dependency.
- TSP upstream release v0.3.37 (2026-11-12); extension-package mechanism is documented upstream. Its current runtime behavior is not verified by this repository.

Review upstream changes and installed versions when starting real integration, not merely these snapshot references.
