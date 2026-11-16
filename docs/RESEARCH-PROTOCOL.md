# Initial research protocol — hypotheses, not profitable strategies

Status: RESEARCH PROPOSAL. No historical full-market replay, prospective validation or economic improvement is claimed.

## Decision problem

Can a Qlib-based model improve **net A-share selection** relative to a transparent, same-information baseline? If so, does independent entry/exit timing improve actual net portfolio decisions rather than just model IC or single-trade win rate?

## Initial controlled study

- Market: Shanghai/Shenzhen A-shares with a point-in-time eligible universe including later-delisted securities. Missing membership/status/adjustment history must be reported and may restrict valid study scope.
- Data: daily bars and trading calendar, original execution prices, declared adjusted/total-return series, suspension/limit states, corporate actions, source coverage and revision/time identity.
- Information cutoff: signals formed after T trading-day close using inputs available by that publication point. No same-close fill. Feasible-order baseline: next eligible session, with an explicitly fixed pricing/execution convention chosen before running. An unfilled order is not a filled trade.
- Primary label hypothesis: ten-trading-day relative ranking of forward tradable-period returns. Predefined secondary horizons: 5 and 20 trading days. Align actual label price basis with chosen entry/exit and adjustments; do not use Qlib's sample default label unchanged.
- Transparent selection baseline: preselected 20-day return ranking. ML candidate: Qlib Alpha158 + LightGBM (initial candidate only, not presupposed winner).
- Training cadence: choose and freeze a feasible time-ordered retraining schedule; daily scoring does not imply daily fitting.
- Initial combination: weekly baseline rebalance with daily *observation* of exit eligibility. A daily observation does not imply an executed trade.

## Incremental experiments

| Identity | Change from comparator | Question |
| --- | --- | --- |
| A | Simple selection + fixed common entry/exit | Does the baseline work economically? |
| B | Replace selection only with ML ranking | Does ML add prediction **and net trading** information? |
| C1/C2 | B plus separate trend/breakout entry rules | Does an entry rule improve net returns beyond exposure reduction? |
| D1/D2 | B plus separate trend/model-deterioration exits | Is exit timing independently useful? |
| E | Predeclared combination, only after separate evidence | Does combined net value persist? |

Initial 20-day MA/20-day high, or other conditions, are **research hypotheses**, not optimized truths. Before conducting a formal comparative experiment, freeze each signal definition, thresholds, data cutoffs, eligible universe, portfolio and execution conditions.

## Required controls

- Same-symbol/date/market membership and equal information availability for paired arms, including unavailable data and missed fills.
- A-share T+1 sell restrictions, relevant board-/security-/period-specific price limits, suspensions, lot sizes, tick sizes, minimum commissions, sell-side stamp duty, fees, spread, slippage, capacity, cash and dividends.
- Chronological train/validation/test segments with appropriate separation for forward labels; no future features, train/test leakage, survivorship bias or ex-post regime selection. Historical periods repeatedly inspected are not fresh holdouts.
- Compare identical funds, starting date, capital and fees. Report period, sample/decision/fill denominators, turnover, gross/net return, return versus buy-and-hold or relevant benchmark, max drawdown, exposure, costs and rejected orders. Report IC separately as diagnostic.
- Avoid cherry-picking the best horizon/parameter from the same OOS set. Record all tested candidates, failures and negative results.

## Acceptance and stopping

Engineering completion means reproducible data transformations and reports, **not** stable alpha. Prediction usefulness means repeatable held-out ranking signal; trading usefulness requires credible after-cost portfolio improvement versus fixed baselines. Prospective observation comes after historical assessment; live trading requires separately confirmed authorization and operational controls.

If data provenance, executable price basis or fundamental corporate-action accounting is untrustworthy, stop promotion of *affected economic claims* rather than inventing backtest returns. Narrow exploratory analysis is acceptable if clearly labeled.

"No trade", "unproven" and "do not adopt" are first-class study outcomes.
