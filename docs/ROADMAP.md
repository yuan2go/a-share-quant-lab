# Current status and qualification gates — 2026-11-16

Scope authorized: implement Tushare data integration, Qlib first-selection study and TSP display boundary. A tool-accessible runtime with the user's local TSP/Qlib instance is NOT available, and external outbound DNS in the development sandbox failed. No token was committed to this public repository.

| Gate | Code status | Actually verified |
| --- | --- | --- |
| Python package and artifact contract | Present | GitHub stdlib tests pass |
| Tushare client, date and units | Present | Synthetic tests pass; user's live proxy not reachable here |
| TSP data-source daily/adj-factor | Present | No running TSP, no actual market pages filled |
| Qlib retrospective data export | Present | Synthetic CSV tests only |
| Official Qlib CSV-to-binary converter | Wrapper present | Not run on real source data |
| Alpha158+LightGBM vs momentum | Research runner present | No actual Qlib training or RankIC output |
| TSP full extension package | Extension + packaging present | No installed/browser-verified extension |
| Manual GitHub study workflow | Workflow_dispatch only | Not run with GitHub Actions secret |
| PIT, prospective, economic Alpha | Not qualified | No real execution account evidence |
| Broker order execution | Not implemented | Not authorized |

## Next gates

1. Confirm the actual proxy permissions and selected Tushare endpoints with a secret-backed source check in a networked runtime.
2. Prove daily price/volume/amount units and discrete vs cumulative adjustment semantics on real corporate-action dates; inspect missing rows and API limits.
3. Generate a genuine local source snapshot, run official Qlib dump_bin and first Alpha158 + LightGBM vs momentum study. Record original artifacts, sample sizes and negative outcomes. Still label historical frozen cohort as retrospective only.
4. In the actual TSP host, install the YAML source and read-only extension and verify stock K-line plus the ranking page after an actual research report exists.
5. Before any trading claims, replace static-cohort selection with qualified historical point-in-time membership, reconcile dividends, constraints, fees, actual order feasibility and run an audited single-authority comparison.

See [runbook](RUN-TUSHARE-QLIB.md). No automatic live trading or GitHub workflow scheduling.
