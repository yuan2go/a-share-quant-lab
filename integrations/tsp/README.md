# TSP adapter — DuckDB data and a read-only Qlib research view

The lab does **not** copy or fork Tick Stock Panel, and its Python Qlib process stays outside TSP's web worker.

## History adapter

First ingest the authorized source into a completed DuckDB capture, then stop the writer and run:

~~~bash
python -m ashare_quant_lab.tsp_gateway --db-path data/market.duckdb
~~~

The gateway accepts historical stock daily/adj_factor requests and queries only the latest COMPLETE DuckDB revisions. It does not send HTTP requests to Tushare. Cumulative factor snapshots are converted to TSP per-event ex_factor; raw prices, shares and CNY are retained.

Copy tushare_aql.yaml into TSP data/data_sources, reload and test it in Settings -> Data sources, then explicitly select both historical datasets and run a small TSP history sync. TSP owns its own display Parquet/DuckDB. The lab's DuckDB remains single-writer: stop gateway when another process ingests source history. Do not expose the unauthenticated gateway to the public Internet.

## Study page

~~~bash
python scripts/package_tsp_extension.py
~~~

Import the trusted ZIP through TSP Settings -> Import and Backup, restart, and load the Qlib research page. Publish a real study result to the existing TSP data directory using aql publish-tsp. It displays research cutoff, model rank scores and status and invokes native TSP stock preview; it does not issue investment or brokerage orders.

Realtime, financial statements, minute data, ETFs, index bars and historical PIT membership are not supplied by this adapter. Actual TSP deployment has not been verified.

Upstream extension contract: https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/extension-packages.md
