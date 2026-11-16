# A-Share Quant Lab

**A-share stock-selection and buy/sell research laboratory** built around [Microsoft Qlib](https://github.com/microsoft/qlib) with an optional [Tick Stock Panel](https://github.com/shy3130/tick-stock-panel) (TSP) Web workbench. This repository does not fork Qlib, vendor TSP or modify existing [MRA](https://github.com/yuan2go/market-regime-alpha) state.

> **As of 2026-11-16: source code and synthetic-data CI checks are present, but the user's Tushare gateway, real Qlib training and running TSP instance have NOT been verified or populated.** No stock-selection performance or profitable strategy has been established. No real-money order functionality.

## Implemented code versus verification

| Area | Code prepared | Still not verified |
| --- | --- | --- |
| Tushare daily data | HTTPS POST for trade_cal/daily/adj_factor, date/price and volume/amount normalization | User's endpoint connectivity and permissions |
| TSP market data adapter | Local HTTP source for stock daily-K and discrete ex-factor, TSP YAML | Actual TSP synchronization and K-line display |
| Qlib data preparation | Immutable retrospective CSV and official Qlib dump_bin wrapper | Real historical data coverage and point-in-time status |
| First Qlib study | Alpha158 + LightGBM vs 20-day momentum, ten-session target and paired RankIC | Actual model run, economics, and generalization |
| TSP Qlib page | Full read-only extension package to show historical ranking and open stock details | Local installation and browser end-to-end test |
| CI and workflow | Unit tests, page syntax/packaging checks, manual-only real-data workflow | Source API and live ML execution |

## Responsibility boundaries

~~~text
Tushare-compatible HTTPS proxy (secret in local environment)
   ├─ TSP daily + adjustment-factor gateway → TSP's original K-line storage/pages
   └─ Immutable retrospective data snapshot
              ↓
       Microsoft Qlib exporter
              ↓
       Qlib Alpha158 + LightGBM
              ↓
       Paired RankIC report (NOT net trading profit)
              ↓
       TSP read-only Qlib research extension
~~~

TSP and Qlib are **dependencies/integrations to be installed in their own runtimes**. They are not copied into this GitHub repository. The code for using them exists, but they are not automatically added to your local computer by a Git commit.

## Fast CLI check

~~~bash
python -m pip install -e .
aql status
python -m unittest discover -s tests -v
python -m ashare_quant_lab.tsp_gateway --help
~~~

Configure TUSHARE_TOKEN only in the running environment and TUSHARE_HTTP_URL=https://t.xiaodefa.top/. The complete install, source test, data synchronization, first Qlib research and TSP extension steps are in:

**[Tushare + Qlib + TSP runbook](docs/RUN-TUSHARE-QLIB.md)**.

[Research protocol](docs/RESEARCH-PROTOCOL.md) · [Prediction artifact contract](docs/RESEARCH-ARTIFACT.md) · [Current scope and gates](docs/ROADMAP.md) · [Architecture](docs/ARCHITECTURE.md) · [Development rules](AGENTS.md)

The initial stock cohort was frozen from a contemporary hand-selected list. Historical PIT data and survivorship-bias controls are not proven. The research runner reports cross-sectional predictive ranking statistics only—not expected win probabilities, trading signals or after-cost profitability.

MIT licensed. No unattended trading authorization.
