# A-Share Quant Lab collaboration rules

Before changes, read README.md, docs/ARCHITECTURE.md, docs/RESEARCH-PROTOCOL.md and docs/ROADMAP.md. Confirm code and real-data runtime separately.

- Purpose: A-share stock selection, buy/sell timing research, true after-cost decision value, with "no trade" as a valid answer. Avoid needless feature expansion and duplicate engines.
- Qlib: external Python dependency for real data science. TSP: independent visualization/workbench host. No Fork, vendoring or silent replacement of their core engines. MRA continues independently.
- Credentials: never commit tokens, secret-bearing MCP URLs, paid raw data or real outputs to Git. Local environment or repository Actions secrets only. The public repo must not expose the user's credential.
- The current study uses a retrospectively fixed cohort and ten-day adjusted-price ranking label; that is not proof of PIT, a dynamic historical universe, unobserved OOS or net trading profitability.
- A valid model score is not an estimated win probability. RankIC, predictive accuracy, trade win rate and account net returns have separate denominators and qualification.
- Tushare cumulative adjustment factors must NOT be written directly to TSP discrete-event ex_factor; normalize volume/amount units, reject source gaps and missing previous snapshots.
- Preserve signal cutoffs, source captured/public times, date/stock coverage, label maturity, actual feasible execution assumptions and all failures. No fabricated live prices or backtest outcomes.
- Before deploying as investment guidance, reconcile historical membership, corporate actions, A-share T+1/limit/ST constraints, fills/costs and genuine prospective or temporally protected results.
- Real broker orders and unattended trading are NOT authorized.
