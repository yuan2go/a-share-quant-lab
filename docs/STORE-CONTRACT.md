# Market storage contract: DuckDB, Parquet and Qlib Binary

Status: IMPLEMENTED + SYNTHETIC DUCKDB/PARQUET INTEGRATION TESTS. Actual Tushare proxy coverage, full Qlib run and TSP deployment remain unverified.

## Storage authority

- DuckDB: source and revision history, one local market-data authority. Its database file is under data/market.duckdb by default.
- Parquet: immutable research snapshot per security, derived from completed DuckDB captures. Each file has SHA256 and a manifest listing contributing capture IDs.
- Qlib Binary: official Qlib dump_bin.py output from the verified Parquet snapshot, never another proprietary market database. The output records input manifest and converter hashes.
- TSP: separate host with its own DuckDB/Parquet UI data. It accesses this lab's completed records by a narrow read-only daily/adj_factor gateway, never shared writable SQL.
- MRA: an independent, untouched existing project.

## Capture and read semantics

DuckDB has captures, daily_bars and trade_sessions tables. Each capture records immutable ID, requested scope, started/completed timestamps, source and state (RUNNING, COMPLETE or FAILED). Daily rows retain symbol/date, raw OHLC, shares, CNY amount, cumulative factor and actual retrieval timestamp. Sessions currently use the source SSE trade calendar.

Each requested batch is committed per security and becomes visible to the research query layer only after the whole capture completes. Failed captures are marked FAILED and their unfinished records removed; prior COMPLETE captures remain intact. Re-ingest creates a new capture rather than updating old observations. For each stock and date, queries choose the latest COMPLETE captured version. Incremental updates can cover a shorter date interval without replacing older completed history.

**DuckDB permits only one writer process per database.** In this first local deployment, stop the TSP read-only gateway before opening a separate ingest writer, then restart the gateway. Multi-process read-while-write is not promised. Backup/restoration should run after closing all DB processes.

## Financial correctness boundaries

- Tushare daily OHLC is unadjusted. Source daily vol is hands (100 shares) and amount is thousands of yuan. Store shares and yuan in DuckDB, without altering the raw OHLC.
- Preserve source cumulative adjustment factor. Qlib research Parquet normalizes it to the first available covered observation and applies it to OHLC and VWAP, inverse-adjusts share volume, and preserves turnover amount.
- TSP event ex_factor is the ratio between consecutive available cumulative factors, NOT the cumulative factor itself. The first observed day is an unknown-baseline day; it does not prove that any earlier corporate action was accounted for.
- If factor, price, VWAP numerator or data coverage is inadequate, reject the affected research export. A market-data source capture does not prove the historical point at which information became publicly available.
- A-share historical securities, delistings, suspensions, board-specific limits and investor cash dividends need independent evidence before claiming executable portfolio gains.

## Snapshot integrity / provenance

Parquet export refuses an existing directory and uses temporary staging then atomic rename. Its schema_version=2 manifest records file_format=parquet, snapshot period, symbol coverage, source_capture_ids, SHA256 per file and explicit RETROSPECTIVE_ONLY status. The converter checks every declared Parquet file and rejects undeclared files, and saves the input manifest hash plus converter hash. The Qlib study checks the same lineage identity before training.

SHA256 and capture timestamps prove local byte lineage, not historical point-in-time validity or economic alpha. Current fixed-cohort study is retrospective and potentially subject to survivorship bias.

## Validation and further upgrades

This change targets repeated Tushare fetches, CSV parsing and source-version ambiguity. Actual runtime performance, disk use, concurrency and correctness on live feeds must be measured before claiming improvements. Do not add another PostgreSQL server, new message queue or second backtest system just for complexity. Only add concurrent-serving projections if a measured need arises.
