# Collaboration rules — A-Share Quant Lab

Read README.md, docs/ARCHITECTURE.md and docs/RESEARCH-PROTOCOL.md before changing research behavior.

## Purpose and boundary
- Optimize verifiable, risk-adjusted **net trading value**, not model count, feature count, CI size or backtest headline numbers.
- Use Microsoft Qlib as the research dependency and TSP as the optional workbench host. Do not vendor or casually fork their engines. Reuse actual supported extension surfaces; inspect installed versions and code before integrating.
- This repository does not authorize automated live trading, changing an existing MRA runtime/database, purchasing data or publishing credentials.

## Evidence discipline
- Explicitly separate: implemented code, local smoke test, source evidence, point-in-time (PIT), held-out validation, prospective observation, simulated trading and actual execution.
- Historical universe/status, source timestamps, adjustment/corporate actions, transaction costs and A-share security-specific trading rules are required for reliable economic conclusions.
- Model scores are arbitrary numerical rankings until calibrated; never label them as probabilities or expected returns by default.
- Respect T-close signal generation versus next feasible execution. Rejected or unfilled orders must not vanish from economic accounting.
- Do not relabel repeatedly inspected histories as unseen OOS. Report negative findings and missing denominators.

## Engineering work
- First inspect existing code/docs and explain why an added capability is needed. Avoid parallel research engines, duplicate backtests and speculative abstractions.
- Choose necessary tests for affected behavior; do not manufacture passing evidence. Keep large/raw data, exports, tokens, account details and Qlib data files out of Git.
- Source code, README claims and successful tests do not prove a strategy profitable or the local Qlib/TSP runtime integrated.
- For the initial project, prioritize a reproducible, real-data Qlib selection experiment and one comparable baseline before developing more UI or research agents.

## Research adoption
Use a primary economic metric, an explicit comparator, time-ordered validation, costs and realistic order rules; record rejected assumptions. "No trade" and "not adopted" are legitimate outcomes.
