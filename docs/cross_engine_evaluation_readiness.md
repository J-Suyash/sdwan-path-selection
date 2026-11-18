# Cross-engine evaluation readiness: measurement audit and smallest informative next experiment

Status: REVIEW DRAFT for the owner, 18 Nov 2026. Nothing here is adopted; the privileged stage needs a fresh scoped approval. Companion: cross_engine_validation_scope_recommendation.md, cross_engine_next_experiment_plan.md, cross_engine_timing_expanded_results.md.

## 1. Measurement definition audit (current state)

| metric | comparability class | instrumentation status after 18 Nov work |
| --- | --- | --- |
| loss_frac | quantity-level, under the three stated conditions (constant 1400 B datagrams, aligned full-run window, explicit end-of-run boundary term) | runner-side accounting verified at sequence-set level in five repeats (r01-r05): capture = qdisc delivered, application log = capture exactly |
| throughput_mbps | quantity-level with documented denominator difference (arrival span vs fixed window) | same verification; denominator caveat stands and is reported per run |
| delay_median_ms | estimator-level only | unchanged; bands measure estimator deviation, never per-packet equality |
| jitter_mean_ms | estimator-level only | unchanged; constant-series mode compares queue/disruption contributions only |
| interruption_s | informative only, never gated (near-circular: emulator value derives from the testbed-calibrated switching model) | unchanged |
| queue_delay_ms | EXCLUDED until an owner-adopted estimator pair exists | unchanged; residence-minus-base candidate still flagged (28% negatives on ce01 smoke) |
| reordering_frac | Mininet-only diagnostic, gate entry OUT-OF-MODEL-SCOPE | unchanged |
| clock-mapped timing | exploratory only | during-send cadence gap closed for future runs (a604831, hardened at the follow-up lifecycle review); today's five runs remain tail-only coverage |

Residual instrumentation limits, stated not hidden:
- 1400/1442 capacity convention is verified on this setup's qdisc counters and is setup-specific; tbf token-consumption length assumption is consistent-evidence-only (no separate rate-precision diagnostic).
- cal_v1/v2 (240 runs) lack per-run receiver/pcap records; not invalidated, not independently verifiable.
- Clock mapping carries declared 1 ms sensitivity assumption and 5 ms detectable-jump alarm; cadence ticks are best-effort under load with per-sample lateness reported and absent labels marking starved ticks.
- The historical buffered-tail defect is strongly supported by exact reproduction, not a proof about any specific historical receive.

## 2. Scenario coverage audit

- ce01 (queue saturation, bulk UDP): exercised heavily; repeatability and accounting now solid for this one scenario. "Sustained sag" remains a working interpretation, not recovered original intent.
- ce02 (voice SLA boundary, 150 ms one-way): the current draft uses 37.5 ms netem delay on five_g, far below the 150 ms threshold; the violation decision is never stressed. Draft preserved unchanged, flagged for owner review.
- ce03 (interactive loss boundary, 5%): the current draft applies zero netem loss; the loss boundary is never stressed. Draft preserved unchanged, flagged for owner review.
- ce04 and cross_engine_cases.json remain as specified; no case currently exercises an SLA decision boundary end-to-end.

## 3. What today's evidence does and does not separate

Across r01-r05 the Mininet loss fraction sits +0.208 to +0.233 pp above the fluid emulator on matched ce01 inputs, with tight repeatability. This single-regime offset cannot be attributed yet: it could be an accounting-convention artifact (1442 B policing, end-of-run boundary term), a queue-model discrepancy that appears only under saturation, or both. One regime cannot separate a constant offset from a regime-dependent model error.

## 4. Smallest scientifically informative next experiment (proposal)

A two-condition matched pair set, both under the existing matched harness, quantity-level gate metrics only:

- Condition A (control): ce01 workload and paths with NO capacity sag (capacity stays above the offered rate). Expected loss near zero on both engines. Purpose: expose any constant accounting/convention offset, including the boundary term, in the absence of queue saturation.
- Condition B (contrast): ce01 as run today (sag into saturation). Already evidenced by r01-r05 on the Mininet side; one or a small number of matched repeats would confirm stability alongside the control.

Decision logic, frozen before data:
- If the offset appears in A as well: points to convention/accounting, not the fluid queue model. Next step is accounting reconciliation, no model conclusion.
- If the offset is absent in A but present in B: points to regime-dependent queue-model discrepancy under saturation, a real model finding worth the owner's interpretation.
- Any other pattern (e.g., large control loss): an instrumentation defect surface; stop and diagnose before any model statement.

Explicit non-goals: no acceptance bands fitted to outcomes, no statistical uncertainty invented beyond raw per-run values and ranges, no timing-gate claims (mapped timing stays exploratory), no SLA-boundary claims (blocked on the ce02/ce03 retune decision, which is the owner's).

## 5. Support vs owner decisions

Support-side (delegated technical judgment, no owner input needed): protocol freezing, instrumentation readiness, boundary-term reporting, runner/sampler mechanics, offline analysis and audits.

Owner decisions (research intent, not delegated): adopting or rejecting gate bands; adopting a queue_delay estimator pair; retuning ce02/ce03 so their named SLA boundaries are actually exercised; interpreting any model discrepancy as a paper claim.

## 6. Execution preconditions

Any Mininet-side run of Conditions A/B requires a fresh scoped user approval (the five-run approval of 16:12 IST is fully consumed). Emulator-side characterization is unprivileged and can proceed offline once the protocol is frozen.
