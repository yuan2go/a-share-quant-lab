# Runbook: Tushare -> DuckDB -> Parquet -> Qlib, plus TSP

**Code and synthetic DuckDB/Parquet CI validated; live provider, local Qlib training and running TSP have not yet been verified.** This public repo must never contain the Tushare token or licensed market history. Do not substitute a successful CI for a real research result.

## 1. Install and verify access

Use Python 3.11. Before source access:

~~~bash
python -m pip install -e '.[storage]'
aql status
aql check-source --start 20260101 --end 20261116
~~~

Pass the token using a local TUSHARE_TOKEN environment variable or a GitHub Actions secret. Default compatible endpoint can be overridden with TUSHARE_HTTP_URL. On PowerShell set the variables in your private shell session. The code calls the official-style Tushare HTTP POST methods trade_cal, daily and adj_factor. It does not call Python SDK pro_bar; if you use that SDK separately, it requires the user's documented api=pro argument.

## 2. Ingest and update DuckDB market history

~~~bash
aql ingest-market --db-path data/market.duckdb --symbols-file configs/first-study-cohort.txt --start 2019-01-02 --end 2026-10-30 --pace-seconds 2
aql market-status --db-path data/market.duckdb
~~~

A capture is accepted only when all requested source calls and per-security records succeed. A FAILED capture is excluded without contaminating earlier completed captures. Later incremental runs use shorter date ranges but the same command; latest COMPLETE version wins for any stock/day.

Do not open the same DuckDB for writing while a separate TSP read-only gateway process has it open. Stop the gateway before ingest and restart afterwards. Actual Tushare permissions/rate limits, historical source continuity and delisted membership are not proven by the command.

## 3. Export one immutable Parquet study snapshot

~~~bash
aql export-qlib-parquet --db-path data/market.duckdb --symbols-file configs/first-study-cohort.txt --start 2019-01-02 --end 2026-10-30 --output-dir data/first-study-parquet
~~~

Parquet files are one per stock, using adjusted prices/volume and a SHA256 manifest with participating complete capture IDs, requested coverage and RETROSPECTIVE_ONLY status. This is not an accounting total-return series. To reproduce, preserve snapshot files together with the manifest. Never overwrite an existing snapshot path.

## 4. Run Qlib with its own Python environment

~~~bash
python -m pip install -e '.[qlib]'
git clone --depth 1 --branch v0.9.7 https://github.com/microsoft/qlib.git qlib-source
aql dump-qlib --qlib-repo qlib-source --snapshot-dir data/first-study-parquet --provider-uri data/first-study-qlib
aql run-first-study --provider-uri data/first-study-qlib --manifest data/first-study-parquet/manifest.json --config configs/first-study.json --output-dir outputs/first-study
aql validate-artifact outputs/first-study/prediction-batch.json
~~~

The official Qlib converter reads Parquet directly and checks the snapshot SHA before conversion. The study compares Alpha158/LightGBM with 20-day momentum on the same available data using mean daily cross-sectional RankIC. The T+1 to T+11 adjusted close label spans 10 trading sessions and is not a real next-session filled trade. Fixed current cohort and past sample examination mean the run is retrospective, not an independent natural forward OOS experiment.

If the source, Qlib conversion, model compatibility, time window or historical data fail, retain the error evidence and stop; do not manufacture a success metric.

## 5. Fill supported TSP pages from the local store

After data ingestion closes its DuckDB writer:

~~~bash
python -m ashare_quant_lab.tsp_gateway --db-path data/market.duckdb
~~~

Copy integrations/tsp/tushare_aql.yaml into your running TSP data/data_sources directory; reload in TSP Settings -> Data sources. First test on a small stock/date range, explicitly select the adapter for daily K and adj_factor, and run the TSP historical synchronization. Compare several stock daily original closing prices, event ratios and share/CNY units with the actual Tushare response before extending it.

TSP keeps its own Parquet/DuckDB history; the gateway never calls the remote provider when TSP opens a chart. Only historical A-share daily bars and adjustment events are supported, not realtime, 1-minute, fundamental/ETF/index feeds. If TSP runs in a different Docker network, its 127.0.0.1 is not the host gateway. The gateway refuses nonloopback binding unless --allow-lan is explicitly provided and the environment is firewalled.

To add the separate historical Qlib ranking page:

~~~bash
python scripts/package_tsp_extension.py
~~~

Import the resulting ZIP through TSP Settings -> Import and Backup, then restart TSP and refresh. No predictions are shown until a **real study** completes. Then:

~~~bash
aql publish-tsp --study-dir outputs/first-study --tsp-data-dir /path/to/existing/tsp/data
~~~

This page is read-only historical research, NOT a current buy/sell signal or trading probability. Actual TSP installation/browser integration has not been verified in this development session.

## 6. Optional manual-only GitHub study run

The workflow in .github/workflows/real-qlib-study.yml requires repository Actions Secret TUSHARE_TOKEN. It creates an ephemeral DuckDB database, Parquet snapshot and Qlib binary in the GitHub runner, then attempts the first real study. It does **not** populate your local TSP; that needs a local data import/sync or an explicitly permitted export of the research report.

This public repository's derived artifacts may be accessible to other readers. Check any paid-data license and confidentiality terms before triggering. No background scheduler, data purchase, or broker order is enabled.
