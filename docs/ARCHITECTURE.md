# Architecture and actual boundary — 2026-11-16

This repository now implements **code**, not a known running investment environment:

- Tushare-compatible HTTPS client, local TSP historical-data gateway and unit/factor normalization.
- CSV export for an immutable retrospective Qlib snapshot, wrapper around official Qlib dump_bin and an Alpha158/LightGBM ranking research runner.
- TSP backend/frontend extension package reading versioned research output, with a CLI that publishes it to an explicitly supplied local TSP data directory.

**Actual user Tushare permissions, stock data quality, Qlib fitting, TSP installation and browser display have not been verified.** No net-profit backtest, open broker connection or real trade.

## Runtime responsibilities

1. Data source and immutable snapshots: pull only authorized Tushare data. Preserve capture time, source, range, SHA and missing-data evidence. Not all historical data are proven available at the stated information timestamp.
2. Independent Qlib process: factor construction, LightGBM training, chronological and purged label segments, research ranking and baseline comparison. This process is NOT started by a TSP Web request.
3. Our project: source adapter, cohort definition, research schema, result qualification, timestamp/status and reporting.
4. Optional TSP host: selected stock daily-K and adjustment data via its existing data-routing mechanism; separate read-only Qlib research page via the documented extension mechanism. Does NOT replace native TSP strategy/backtest engine.
5. MRA: separate existing system, untouched.

## Financial meaning and source constraints

Tushare daily volume is in 100-share lots and amount is in thousand CNY. The TSP app expects shares and CNY, and its ex_factor is an individual event ratio rather than Tushare's cumulative adj_factor. The adapter converts both; missing pre-window factor history is a hard error except a full-from-1990 historical baseline.

The Qlib train/test target from T+1 close to T+11 close is a historical label, **not a fillable profit account**. Static cohort chosen today may exhibit survivorship/selection bias. A positive RankIC result would only demonstrate retrospective ranking evidence. To claim economic gain, first implement equivalent realistic orders/costs, company actions, historical dynamic universe, and honest held-out/prospective testing.

## Upstream references

- Qlib PyPI optional dependency pyqlib==0.9.7, official matching source converter from tag v0.9.7.
- TSP v0.3.37 backend extension API v1 and Page Pack SDK v1. Never package Qlib's compiled ML dependencies into TSP's web-worker ZIP.
- User-provided compatible Tushare HTTPS POST endpoint. Real permissions unknown.

See [runbook](RUN-TUSHARE-QLIB.md) and [status](ROADMAP.md).
