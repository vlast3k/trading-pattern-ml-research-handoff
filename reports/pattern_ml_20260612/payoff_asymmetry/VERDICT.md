# Payoff-Asymmetry Review

Primary objective: winners must outweigh losers by enough to create robust expectancy. A high win rate is neither required nor sufficient.

## Frozen Metrics

- Payoff ratio: average winner / average loser.
- Profit factor: total winning dollars / total losing dollars.
- Edge margin: observed win rate minus the break-even win rate implied by the payoff ratio.
- Point-estimate gate: payoff ratio >= 1.30, profit factor >= 1.20, edge margin >= 3%, positive expectancy, and profit factor >= 1.0 after removing the largest winner.
- Confidence gate: at least 20 trades with at least five winners and five losers, plus 95% bootstrap lower bounds above break-even for payoff ratio, profit factor, and expectancy.
- Period results below include commission but no added slippage, matching the existing formula baseline. The cost-sensitivity table applies additional MNQ slippage.

## Period Results

| Period | Trades | Win rate | Avg win | Avg loss | Payoff | Profit factor | Expectancy | PF without largest winner | Point gate | Confidence gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `early_development` | 47 | 42.6% | $+47.85 | $27.31 | 1.75 | 1.30 | $+4.67 | 1.17 | pass | fail |
| `late_development` | 83 | 36.1% | $+36.69 | $30.74 | 1.19 | 0.68 | $-6.37 | 0.62 | fail | fail |
| `validation` | 19 | 63.2% | $+61.19 | $41.12 | 1.49 | 2.55 | $+23.49 | 2.18 | pass | fail |
| `final_test` | 80 | 52.5% | $+47.78 | $30.56 | 1.56 | 1.73 | $+10.57 | 1.64 | pass | pass |

## Confidence

| Period | Payoff 95% CI | Profit factor 95% CI | Expectancy 95% CI | P(PF >= gate) | P(E > 0) |
|---|---:|---:|---:|---:|---:|
| `early_development` | 1.29 to 2.31 | 0.63 to 2.46 | $-7.32 to $+16.95 | 57.7% | 77.2% |
| `late_development` | 0.90 to 1.52 | 0.38 to 1.11 | $-14.26 to $+1.77 | 1.3% | 6.5% |
| `validation` | 0.97 to 2.43 | 0.93 to 8.72 | $-1.74 to $+48.10 | 93.6% | 96.7% |
| `final_test` | 1.26 to 1.95 | 1.06 to 2.76 | $+1.13 to $+19.87 | 92.8% | 98.5% |

## Slippage Sensitivity

| Period | Slippage ticks / side | Payoff | Profit factor | Expectancy | PF without largest winner | Net PnL |
|---|---:|---:|---:|---:|---:|---:|
| `early_development` | 0 | 1.75 | 1.30 | $+4.67 | 1.17 | $+219.44 |
| `late_development` | 0 | 1.19 | 0.68 | $-6.37 | 0.62 | $-528.84 |
| `validation` | 0 | 1.49 | 2.55 | $+23.49 | 2.18 | $+446.38 |
| `final_test` | 0 | 1.56 | 1.73 | $+10.57 | 1.64 | $+845.60 |
| `early_development` | 1 | 1.65 | 1.23 | $+3.67 | 1.11 | $+172.44 |
| `late_development` | 1 | 1.12 | 0.64 | $-7.37 | 0.58 | $-611.84 |
| `validation` | 1 | 1.43 | 2.45 | $+22.49 | 2.09 | $+427.38 |
| `final_test` | 1 | 1.48 | 1.64 | $+9.57 | 1.56 | $+765.60 |
| `early_development` | 2 | 1.56 | 1.16 | $+2.67 | 1.05 | $+125.44 |
| `late_development` | 2 | 1.06 | 0.60 | $-8.37 | 0.55 | $-694.84 |
| `validation` | 2 | 1.37 | 2.35 | $+21.49 | 2.00 | $+408.38 |
| `final_test` | 2 | 1.41 | 1.55 | $+8.57 | 1.47 | $+685.60 |
| `early_development` | 4 | 1.40 | 1.04 | $+0.67 | 0.93 | $+31.44 |
| `late_development` | 4 | 0.94 | 0.53 | $-10.37 | 0.49 | $-860.84 |
| `validation` | 4 | 1.27 | 2.17 | $+19.49 | 1.85 | $+370.38 |
| `final_test` | 4 | 1.27 | 1.40 | $+6.57 | 1.33 | $+525.60 |

## Interpretation

Validation and final-test winners are materially larger than losers, so the candidate's recent profit is not merely a high-win-rate effect.
However, payoff asymmetry was not stable through development. Late development had insufficient winner size and total gross profit to cover losses.

**Verdict: optimize the review around payoff asymmetry, but do not optimize the strategy on these historical blocks. The prospective gate must prove that winners remain larger than losers and that gross wins exceed gross losses after removing the largest winner.**

Supporting files: `period_payoff.csv`, `cohort_payoff.csv`, `rolling_payoff.csv`, `cost_sensitivity.csv`, and `gate.json`.
