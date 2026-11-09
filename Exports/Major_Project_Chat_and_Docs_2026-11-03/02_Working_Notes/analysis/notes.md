# Lab notebook (running results log)

Plan Section 14.2: date, config, seeds, numbers, one-line conclusion.

## 2026-10-31 — baseline comparison, first pass

Environment: emulator at commit 98c0349 (traces: bb=collected,
five_g=lumos5g, leo=wetlinks). Episode 1 h. Trained 100k steps, CPU.

| policy | cost/h | voice viol/h | switches/min | note |
|---|---|---|---|---|
| threshold n5 m30 (incumbent) | 0.42 | ~3 | ~0 | strong, benign traces |
| best quality | 1.45 | ~2 | high | expensive, safe |
| lowest cost within SLA | 0.29 | ~80 | — | cheap, risky |
| DQN online (3 seeds) | 0.19 | 3296 | 0 | ignores SLA entirely: proof that unconstrained RL is unsafe |
| Lagrangian PPO (3 seeds, lam 50/25) | 0.28–0.96 | 3223–79 | 1.7–16.8 | unstable, under-tuned |
| Lagrangian PPO (1 seed, lam 200/100, eta 0.2) | 0.56 | 529 | 13.0 | better but dominated by incumbent |

Conclusions:

- The incumbent threshold rule is strong on mostly-benign traces; beating
  it on cost without more violations is a real challenge (good for the
  paper's credibility).
- Unconstrained DQN minimizes cost by parking everything on broadband and
  violating voice ~91% of the time — the exact motivation for constrained
  methods.
- Lagrangian PPO needs a proper multiplier/training sweep (Phase 5).

Known calibration items:

- Trace RTT is treated as one-way delay in the emulator; broadband
  (~188 ms RTT) therefore never meets the 150 ms voice delay SLA. Either
  halve RTT when mapping to one-way delay or revisit SLA thresholds in
  the Phase 4 Mininet calibration. Affects absolute violation counts,
  not the relative ranking of policies.

## 2026-11-01 — Phase 3 first offline runs

| algo | dataset | cost/h | voice viol/h | switches/min | note |
|---|---|---|---|---|---|
| discrete BC | d1 | 0.421 | 3.0 | 0.05 | matches incumbent (0.42/3): data pipeline sound |
| discrete BC | d2 | 0.421 | 2.0 | 0.05 | mixture still imitates threshold-like behavior |
| discrete CQL | d1 | 0.421 | 5.6 | 0.13 | conservative: no cost-minimizing collapse, but no gain yet |

Conclusions:

- BC reproduces the incumbent almost exactly on D1, passing the Week 10
  sanity check from the plan.
- CQL stays near the incumbent instead of finding the unsafe cheap
  policy (contrast with online DQN: 0.19 cost, 3296 violations) — the
  intended conservative behavior. Gains over the incumbent need tuning:
  alpha, n_critics, encoder size, more steps, and the constraint critics.

Next:

- Discrete IQL is not in d3rlpy 2.8 — implement it by hand (expectile
  regression + advantage-weighted extraction).
- Constraint critics for SLA violations and switches + Lagrangian
  policy selection.
- Off-policy evaluation (fitted-Q + WIS + bootstrap) and the acceptance
  test.
