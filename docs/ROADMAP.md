# Current evidence and next gates — 2026-11-16

The source database refactor is implemented and synthetically tested. **No user-specific live Tushare request, local Qlib training run or mounted TSP page has been performed in the current session.**

| Area | Code status | Actual verification |
| --- | --- | --- |
| Independent Python application + optional official Qlib | Present | Package, CLI, CI passed |
| Tushare client + raw unit conversion | Present | Synthetic tests; live provider UNKNOWN |
| DuckDB full/failed capture history | Present | Native DuckDB write/read, latest COMPLETE revision and failure rejection in CI |
| DuckDB to frozen Parquet | Present | Native Parquet value/coverage checks in CI |
| Official Qlib converter | Parquet supported, manifest SHA and converter lineage check | Not run on actual real-data Qlib Binary |
| Alpha158 and LightGBM vs simple momentum | Existing research entry | Not trained on user's real dataset; no RankIC/outcome |
| TSP market gateway | Reads complete DuckDB captures instead of remote provider | Handler tested; not deployed in TSP |
| TSP result viewer | Existing read-only extension | Packaging/JS syntax only; no browser E2E |
| Historical PIT/dynamic universe | Not qualified | Current cohort is fixed retrospectively |
| Live/net profitable orders | Not implemented | Not authorized |

## Next valuable checks

1. Verify the Tushare source API with actual secret-backed network access and check source coverage/units/permissions.
2. Capture real historical bars/factors/calendar in DuckDB, freeze a Parquet snapshot with hashes, and run the actual official Qlib conversion + LightGBM/momentum experiment. Preserve failures and original evidence.
3. Install and locally validate TSP daily/adj_factor data source and historical research page. Confirm displays against the same source snapshot, not just UI presence.
4. Before investing or optimizing buy/sell signals, establish dynamic historical membership, PIT/label availability, corporate actions, realistic A-share order constraints and single comparable after-cost portfolio performance.

Do not add another generic DB, front end, agent or strategy engine until a measured bottleneck or observed decision advantage makes it necessary. Future changes should target real-data coverage and a verified economic result rather than feature count.
