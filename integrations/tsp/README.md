# TSP integration plan (NOT IMPLEMENTED)

This directory marks the intended boundary; it is **not** a ready-to-install TSP extension.

Selected host: https://github.com/shy3130/tick-stock-panel
Initial upstream reference: v0.3.37, not checked against the user's local installation.

Prefer the documented extension package / backend router / Page Pack SDK APIs:
- https://github.com/shy3130/tick-stock-panel/blob/main/docs/extension-packages.md
- https://github.com/shy3130/tick-stock-panel/blob/main/docs/page-sdk.md
- https://github.com/shy3130/tick-stock-panel/blob/main/docs/secondary-development.md

Intended split:
- Qlib runs as a separate research worker with independent dependencies/data snapshots. Do not put training into the TSP web process.
- A read-only API loads **validated** immutable prediction artifacts, returns explicit staleness/coverage/unverified status, and never implies a score is a buy recommendation.
- A TSP page lists experimental ranking results; stock row click reuses the host's stock-preview capability. No duplicate K-line chart implementation.
- Exact signal cutoff and published time must remain visible. No browser route is allowed to trigger real orders or write MRA state.

TSP supports extensions but its documented core selection-scoring and backtest engines are **not** generally replaceable through all extension APIs. Do not claim that an external Qlib score can automatically be injected into them; research display integration comes first.

Implementation requires checking the actual running TSP source/version and the extension API, building and testing a package, and verifying a real Qlib result end-to-end. No such test has yet been run.
