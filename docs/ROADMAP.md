# Current project state and next acceptance gates

As of 2026-11-16. Update this record based on real code, actual datasets and observed executions, not a plan alone.

| Gate | Status | Evidence / remaining work |
| --- | --- | --- |
| Repository bootstrap | IMPLEMENTED, awaiting GitHub CI observation | Python package, CLI, schema validator, docs, stdlib tests |
| Local Qlib data probe | CODE PRESENT, NOT RUN ON USER DATA | Optional pyqlib and existing local data path required |
| Historical A-share PIT data | NOT VERIFIED | Provider access, dynamic universe, timestamps, corporate actions |
| Qlib Alpha158 / LightGBM | NOT IMPLEMENTED | One reproducible 10-day ranking experiment against simple baseline |
| Buy/sell timing research | NOT IMPLEMENTED | Entry and exit decision effects with common execution/cost basis |
| TSP extension integration | NOT IMPLEMENTED | Read-only artifact display, reuse existing stock preview |
| Natural prospective monitoring | NOT STARTED | Frozen result identity and non-lookahead daily observation |
| Real trading | NOT AUTHORIZED | No brokerage integration in scope |

## Next work in dependency order

1. Confirm installed Qlib version/provider path and run the local-data probe on a real stock/time range; independently check Tushare historical permission and original source coverage. No credential is committed.
2. Define symbol/date/corporate-action/PIT mapping; generate one dated, immutable data snapshot and coverage report. If historical point-in-time proof is missing, explicitly label exploratory results.
3. Implement one Qlib 10-trading-day ranking study against a transparent 20-day momentum baseline with matching universe and time conventions; report OOS forecast metrics and actual paired economics, including failures.
4. Only after adequate selection evidence, isolate entry and exit rules to measure their incremental net effect.
5. Then implement TSP extension reader, stock preview binding and research card. Avoid a premature second backtesting interface.
6. Evaluate whether a versioned result adapter to MRA improves decision/execution evidence; do not merge projects by default.

## External baseline references
- Qlib: https://github.com/microsoft/qlib
- TSP: https://github.com/shy3130/tick-stock-panel
- MRA: https://github.com/yuan2go/market-regime-alpha
