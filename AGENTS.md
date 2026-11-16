# A-Share Quant Lab — active collaboration rules

Before production changes, read README.md, docs/ARCHITECTURE.md, docs/STORE-CONTRACT.md, docs/RESEARCH-PROTOCOL.md and docs/ROADMAP.md. Current code and actual evidence outrank stale prose. Preserve negative research and necessary history while retiring obsolete current entrypoints.

- Goal: independent A-share stock-selection/buy-sell research laboratory that tests robust, executable after-cost economic value. No trade and do-not-adopt are valid.
- Qlib is the external data/factor/model/research dependency; TSP is the independent supported UI host; MRA remains a separate system. No Qlib/TSP fork, duplicate backtest engine, new DB cluster, complex agent platform or auto broker order without demonstrated need and authorization.
- DuckDB is the local source database of versioned Tushare market captures. COMPLETE vs FAILED must be respected. Parquet is immutable research projection with SHA and contributing capture IDs. Qlib Binary is official conversion; TSP owns a separate display copy. Do not permit competing market-data authorities.
- Credentials must stay outside public Git, URLs and model artifacts; use local environment or secret manager. Historical source capture time does not imply prior public availability or strict PIT. Fixed present-day sample is RETROSPECTIVE_ONLY and vulnerable to survivorship bias.
- Tushare volume hand-to-share and amount thousand-CNY-to-CNY conversion must be correct. Cumulative adj_factor is not TSP event ex_factor. Do not invent missing VWAP or other source fields.
- DuckDB is single-writer. Stop TSP gateway when a separate DB ingest runs; validate that the latest complete capture is what Qlib and TSP actually consume.
- Scores, RankIC, win rates, feasible trades and after-cost accounts are different. Verify exact information/cutoff/label times, dynamic membership, corporate actions, security-specific trading rules, costs and unfilled orders before claiming economic alpha or buy/sell effectiveness.
- Choose necessary risk-based tests. CI on synthetic data is not real proxy, local TSP, Qlib training, PIT or trading evidence. Keep both successful and negative experimental artifacts.
