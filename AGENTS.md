# Resonance Reversal Project Rules

## Scope

- This repository contains only the independent `resonance_reversal_strategy`.
- Only the strategy, its `research` tools, documentation, and `test_resonance*.py` tests are in scope.
- Other strategies may be inspected read-only as design references, including
  their source code, documentation, and already-existing backtest evidence.
- `resonance_reversal_strategy` remains the only strategy that may be modified,
  run, or validated from this project. Do not modify, run, or validate a
  referenced strategy.
- Do not directly copy another strategy's code, parameters, or performance
  conclusions. Convert any referenced design into an independently stated
  hypothesis, then pre-register and validate it within this strategy's own
  training boundary before considering adoption.
- Do not use another strategy's validation-period or full-period results to
  tune this strategy.

## Working Process

- Before every code or behavior change, analyze the relevant context, present a Chinese implementation plan and impact boundary, and wait for explicit user approval.
- Apply the minimum-change principle. Do not alter unrelated files, formatting, parameters, reports, or behavior.
- Use test-driven development for implementation changes and run only the dedicated resonance tests.
- Complete each verified milestone with a summary and a Git commit.

## Data and Research Boundaries

- Daily signals may use only T-1 and earlier data. T-day execution data must not revise a frozen signal, rank, size, or sell decision.
- The 2019-2021 training period may use pre-2019 data only as read-only warm-up for rolling indicators; warm-up data must not enter returns, tuning, or rule selection.
- Do not use validation-period or full-period results to tune parameters, thresholds, indicators, or rules.
- JoinQuant backtests remain authoritative for strategy performance. Local research is read-only diagnostic work unless a separately approved design states otherwise.

## Protected Behavior

- Preserve the current ATR observation-only policy unless a separately approved strategy change explicitly replaces it.
- Preserve training manifests, log identity checks, source immutability, friction comparison, and fail-closed evidence validation.
- Research reports must never silently become trading rules or candidates.
