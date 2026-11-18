# Cross-engine evaluation readiness: measurement audit and smallest informative next experiment

Status: REVIEW DRAFT for the owner, 18 Nov 2026 (revised after review: causal decision logic replaced by diagnostic-lead framing). Nothing here is adopted; the privileged stage needs a fresh scoped approval. Companion: cross_engine_validation_scope_recommendation.md, cross_engine_next_experiment_plan.md, cross_engine_timing_expanded_results.md.

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
| clock-mapped timing | exploratory only | during-send cadence gap closed for future runs (a604831, hardened 129309d: try/finally stop/join on every exit path, per-tick lateness reported, starved ticks visible as missing labels); today's five runs remain tail-only coverage |

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

## 3. The open question today's evidence cannot answer

Across r01-r05 the Mininet loss fraction sits +0.208 to +0.233 pp above the fluid emulator on matched ce01 inputs, tightly repeated. One regime cannot attribute this offset. Candidate families: accounting/convention artifacts (1442 B policing, end-of-run boundary term), a queue-model discrepancy that appears only under saturation, or an interaction. Accounting differences can themselves be load-dependent, so a control-condition pattern alone cannot deliver a causal verdict either.

## 4. Smallest informative next step (proposal): control + contrast pair as diagnostic leads

Frozen inputs:
- Condition B (contrast): `testbed/scenarios/case_drafts/ce01.json` unchanged, sha256 f4944ae2e2db1c66c831b3042df04059702d33d9bf5138c3852ad41003e741e8 at 9f1acd3.
- Condition A (control): `testbed/scenarios/case_drafts/ce01_control_nosag.json`, byte-identical to ce01.json except `"events": []` and the name/review fields, so offered 60 Mbps stays below five_g nominal 150 Mbps for the whole run. Hash recorded at execution time in the scope evidence.

How to read outcomes (frozen before data): the A/B loss-offset pattern is a diagnostic lead, never a verdict. Each lead names the mechanism checks that discriminate it:
- Offset present in both A and B: lead toward convention/accounting. Mechanism checks: qdisc counter conservation per run, capture sequence-set audit, end-of-run boundary term size, 1442 B policing arithmetic on actual counters.
- Offset absent in A, present in B: lead toward regime-dependent queue behavior under saturation. Mechanism checks: per-inspection backlog series vs emulator occupancy trace, drop placement within the window, netem/tbf counter split, emulator queue accounting path (env/queue.py) under the same inputs.
- Material loss in A (control): lead toward configured queue/burst behavior or an instrumentation surface. Mechanism checks: which qdisc dropped, burst/limit parameters on the actual installed chain, capture drop counters - genuine configured behavior is itself a reportable finding, not an automatic instrumentation verdict.

Stop rules are mechanical evidence-completeness only, identical in kind to the five-run scope: source-hash mismatch, output-dir collision, namespace/bridge/port collision, instrumentation incompleteness, or cleanup failure stops the series. No numeric outcome is a stop condition; adverse or unexpected results are preserved and reported, never replaced.

Repetition rationale and resource effects: 5 runs per condition, matching the established n=5 contrast set, so raw per-run values and ranges sit side by side without invented statistics. Each Mininet run: ~14 s send inside a ~19 s horizon plus setup/teardown (~60-90 s wall total), ~75k packets, ~30 MB artifacts, sudo-required network namespace lifecycle identical to the approved five-run shape, s1 untouched, per-run cleanup verification. Two conditions x 5 runs = 10 runs, ~15-20 minutes total wall including per-run verification.

Emulator side is unprivileged and runs offline under scripts/run_emulator_matched_case.py for both conditions (control + contrast), seeds and repetitions recorded, all artifacts labeled raw_unvalidated_scaffolding.

Explicit non-goals: no acceptance bands fitted to outcomes, no statistical uncertainty beyond raw per-run values and ranges, no timing-gate claims, no SLA-boundary claims (blocked on the owner ce02/ce03 retune decision), no causal claim from the pattern alone.

## 5. Support vs owner decisions

Support-side (delegated technical judgment): protocol freezing, instrumentation readiness, boundary-term reporting, runner/sampler mechanics, offline analysis, emulator characterization, mechanism-check execution.

Owner decisions (research intent, not delegated): adopting or rejecting gate bands; adopting a queue_delay estimator pair; retuning ce02/ce03 so their named SLA boundaries are actually exercised; interpreting any model discrepancy as a paper claim; accepting the "sustained sag" reading of ce01.

## 6. Execution preconditions

Any Mininet-side run requires a fresh scoped user approval (the five-run approval of 16:12 IST is fully consumed). Emulator-side characterization is unprivileged and proceeds offline. The approval-ready Mininet scope is section 4 above with per-run checks identical in kind to the executed five-run scope (fresh hashes, preflight, no detached suite, output absence, per-run cleanup and s1 verification, stop-on-incompleteness).
