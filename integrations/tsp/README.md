# TSP integration — source code present; host not yet deployed

Our extension uses the TSP v0.3.37 Full Extension Package contract and remains independent of both Qlib's Python environment and TSP's strategy engine.

- Data source: [tushare_aql.yaml](tushare_aql.yaml), supports stock daily OHLCV and discrete-event adjustment factors only. Launch the localhost Tushare proxy in the appropriate network and choose the source in TSP Settings → Data sources. It does not provide realtime, ETF/index or minute data.
- Research page: full extension package in this directory (extension.yaml, backend/, frontend/). Package with python scripts/package_tsp_extension.py; import in TSP Settings → Import and Backup, restart and refresh.
- Outputs: after the separate Qlib retrospective ranking study, aql publish-tsp writes the checked result to TSP's existing local data/aql/ directory. The page shows historical ranking and opens the original TSP stock preview, never trading advice.

The host data-provider and extension have not been installed or tested against a live TSP. All display and actual K-line coverage claims require local end-to-end verification.

Upstream: https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/extension-packages.md
