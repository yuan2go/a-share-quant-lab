# Tushare + Qlib + TSP runbook

**State: source and adapters implemented, user gateway, actual Qlib training, and running TSP not yet verified.** The repository is public. Keep the user's Tushare token ONLY in a local environment variable or GitHub Actions secret; never commit it or place it in a URL.

## Capability boundaries

The Tushare HTTP adapter supports trade_cal, daily and cumulative adj_factor using the documented HTTPS POST protocol. TSP's daily and per-event adjustment-factor sources are exposed by a small local HTTP adapter. The Qlib training process uses the official Alpha158 and LightGBM APIs as a separate Python dependency. The TSP Qlib study page reads historical research artifacts only and is NOT a live BUY/SELL service.

No realtime quotes, minute bars, ETF/index bars, complete corporate action accounting, full PIT historical universe, broker orders or trading profitability are provided by this phase.

## 1. First confirm the source API

Install the repo core in Python 3.11 and set the private token in your own shell:

~~~bash
python -m pip install -e .
# In your terminal, supply TUSHARE_TOKEN from your private secret manager.
export TUSHARE_HTTP_URL=https://t.xiaodefa.top/
aql check-source --start 20260101 --end 20261116
~~~

PowerShell uses env:TUSHARE_TOKEN and env:TUSHARE_HTTP_URL environment variables. The token is never printed. If the request fails, stop and record actual error, permission and source coverage. Do not mark source ready merely because the client code exists.

These paths call standard daily and adj_factor endpoints, NOT the Python-SDK-only pro_bar wrapper. When calling pro_bar directly outside this application, follow the original user requirement to pass api=pro.

## 2. Populate supported TSP daily-K data locally

Run the local adapter in the network and Python environment where it can reach the HTTPS proxy:

~~~bash
python -m ashare_quant_lab.tsp_gateway
~~~

Copy integrations/tsp/tushare_aql.yaml to the running TSP's data/data_sources/tushare_aql.yaml. TSP and this adapter must share a network; inside Docker, 127.0.0.1 means the TSP container, not the host. A private shared network is preferable; exposing an unauthenticated adapter outside loopback needs tight firewall restrictions.

In TSP Settings → Data sources, reload configs. Test the daily AND adj_factor capabilities for a small known stock/date range; choose this provider explicitly for both and trigger a limited historical sync. Check K-line original prices and adjustments against upstream data before extending scope. The adapter handles missing TSP start/end timestamps as full backfills from 1990 in bounded date partitions, not partial default 1-year history.

**Critical unit and factor semantics:** Tushare daily volume is in 100-share hands; Tushare amount is in thousands of CNY. Convert to shares and CNY for TSP. Tushare cumulative adj_factor is NOT TSP's single-event ex_factor: the adapter explicitly ratios adjacent snapshots. It does not invent a previous factor when a request starts midway through the lifetime and no earlier snapshot is available.

TSP pages only display what TSP itself successfully ingests. No running TSP instance has been provided here, so its actual pages have not been filled. This adapter does not advertise realtime/minute/financial/ETF/index data.

## 3. Export a frozen retrospective Qlib dataset

The versioned first-study-cohort.txt is a fixed present-day sample. This choice produces survivorship-selection bias; historical dynamic constituent membership is not verified. It is only a first research engineering/retrospective comparison.

~~~bash
aql export-qlib-csv \
  --symbols-file configs/first-study-cohort.txt \
  --start 2019-01-02 --end 2026-10-30 \
  --output-dir data/first-study-csv \
  --pace-seconds 2
~~~

CSV output is separate from Git, immutable by directory path, and includes a manifest with file hashes, capture time and retrospective/PIT warnings. Adjusted signals are built from raw OHLC multiplied by cumulative Tushare factor relative to the first valid factor; volume is inverse-adjusted and amount is in CNY. Do not interpret these signals as account total returns or dividend cash flows.

## 4. Run the official Qlib converter and ML comparison

Use an isolated Python/Qlib environment, NOT the TSP HTTP worker:

~~~bash
python -m pip install -e '.[qlib]' fire
git clone --depth 1 --branch v0.9.7 https://github.com/microsoft/qlib.git qlib-source

aql dump-qlib \
  --qlib-repo qlib-source \
  --csv-dir data/first-study-csv \
  --provider-uri data/first-study-qlib

aql run-first-study \
  --provider-uri data/first-study-qlib \
  --manifest data/first-study-csv/manifest.json \
  --config configs/first-study.json \
  --output-dir outputs/first-study

aql validate-artifact outputs/first-study/prediction-batch.json
~~~

Study target: ranking of 10-session adjusted-price returns from T+1 close to T+11 close. Train 2019–2022; validate 2023; test 2024–2026-09-30. A label embargo of at least 11 trading sessions separates time splits. LightGBM + Alpha158 and the 20-session momentum baseline use the same available date/symbol pairs. Outputs include mean daily cross-sectional RankIC, observations and pair counts. They DO NOT include realistic trades, commissions, slippage, dividends or net profits. Chronological test is not equivalent to independent real-world prospective data, especially for the current selected cohort.

Abort on missing data, invalid universe or immature labels rather than report a manufactured result.

## 5. Install the read-only TSP research page

~~~bash
python scripts/package_tsp_extension.py
~~~

Import the resulting dist/aql-tsp-extension.zip in TSP Settings → Import and Backup. Follow the TSP extension review/installation prompt, restart TSP and refresh the browser. The Qlib 研究 page starts EMPTY. After an actual study completes:

~~~bash
aql publish-tsp \
  --study-dir outputs/first-study \
  --tsp-data-dir /path/to/existing/tsp/data
~~~

It reads local data/aql/latest-prediction.json and latest-report.json through the TSP extension endpoint, showing historical scores, forecast dates and rank-IC diagnostics with explicit unqualified status. Stock rows use the TSP stock-preview bridge. The TSP v0.3.37 page API bridge does not have a generic extension-route request method: the packaged page uses one fixed, same-origin, session-aware GET; no API key or broker write.

The running TSP extension package has not been installed or observed in this environment. If its API differs, update the adapter after verifying the actual host version rather than copying its core pages.

## 6. Run via GitHub Actions instead of a local ML machine

A **manual-only** workflow is provided in .github/workflows/real-qlib-study.yml. Because this repository is public, add TUSHARE_TOKEN as a repository **Actions secret**, not a plaintext variable. Then choose Actions → A-share first real-data research (manual) → Run workflow. It fails early when the secret is missing. If successful it exposes the report/prediction output as an Actions artifact for seven days, **not raw commercial market data**. Bear in mind report artifacts in a public repository may be accessible to others. The workflow does not deploy TSP or place files on your local machine.

No scheduled background data import or real-money trading is enabled. Actual source and ML execution remain to be independently verified.
