# Active architecture — independent Qlib research application

The earlier user-approved design remains the authority: develop an independent Python application, use official Qlib as a dependency, and let TSP supply existing pages/stock charts. No new repository, no Qlib/TSP fork, no MRA migration.

## Focused adjustment

| Component | Previous | Current |
| --- | --- | --- |
| Historical data | Tushare -> direct CSV plus TSP gateway making separate remote calls | Tushare -> DuckDB complete/versioned capture, TSP read-only from local DB |
| Research data transfer | CSV intermediate | Immutable compressed Parquet with manifest and hashes |
| Qlib format | Official dump_bin | Still official dump_bin with Parquet suffix; same model engine |
| Models | Alpha158 LightGBM vs momentum | Research hypothesis unchanged; snapshot-to-binary identity verified |
| UI | Independent TSP extension | Unchanged; TSP itself stores its own rendering cache |
| Execution / MRA | Out of scope | Unchanged; no broker and no MRA database changes |

~~~text
User-licensed Tushare source
     |
     v
Local DuckDB source captures (one writer)
     |---- TSP historical source HTTP reader --> TSP native pages
     |
     v
Frozen per-stock Parquet (capture IDs + file hashes)
     |
     v
Official Qlib binary converter
     |
     v
Qlib feature/model/research workflow --> tested ranking diagnostics
     |
     v
TSP separate read-only Qlib research extension
~~~

## Boundaries and limitations

There is no second independent ML framework, stock-trading execution engine, broker integration, market-wide real-time feed, Java/React rewrite, Kafka queue or default PostgreSQL server. The existing flat Python source package is sufficient; add deeper selection/timing modules only when research actually requires them.

Current GitHub CI checks database/Parquet native read/write, source normalization, failure isolation, schema/lineage and extension syntax on synthetic records. Real Tushare availability, actual Qlib LightGBM metrics and TSP UI rendering are NOT yet verified.

The Qlib study uses a ten-trading-day adjusted-price label, not a fillable order. It remains fixed-cohort retrospective and has no historical dynamic/PIT certification or real after-cost account results. Future net Alpha comparison needs one audited execution and cost authority.

See STORE-CONTRACT.md, RESEARCH-PROTOCOL.md and RUN-TUSHARE-QLIB.md.
