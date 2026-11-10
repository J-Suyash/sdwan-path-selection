# RTT semantics and SLA audit

Deliverable for verification spec section 3. Status: **PASS** for the
semantics fix and its regression coverage; the violation decomposition
is **complete for seeds 0–2, medium profile** and revises one earlier
assumption (violations are congestion-driven, not outage-driven).

## 1. RTT / one-way-delay semantics

Verified semantics (owner decision 5): SLA delay thresholds are one-way
(ITU-T G.114); every trace delay input is a round-trip measurement.

| Source | Delay field | Semantics | Pinning status |
| --- | --- | --- | --- |
| WetLinks | `ping_avg` | round-trip ping | verified, pinned |
| Raca5G | `PINGAVG` | round-trip ping | verified, pinned |
| LENS | `rtt` | round-trip; `IRTT` column is one-way | **per-field pinning required before any LENS adoption** |
| Lumos5G | — | no RTT field | excluded from delay evidence |
| collected/RIPE-Atlas | ping | round-trip | verified |

The fix applies `oneway_delay_factor = 0.5` exactly once, in
`SDWanEnv._class_qos` (`delay_rtt = rtt * factor`) and identically in
the incumbent check `policies.incumbents.link_ok`, so controller and
emulator agree on SLA semantics.

## 2. Regression coverage (`tests/test_rtt_semantics.py`, 8 tests)

| Property | Test |
| --- | --- |
| 200 ms RTT maps to 100 ms one-way SLA input | `test_rtt_200_maps_to_oneway_100` |
| Factor applied once in emulator delay; config not mutated by evaluation | `test_factor_applied_once_in_emulator_delay` |
| Observation features carry raw round-trip RTT (not halved) | `test_raw_rtt_is_preserved_in_observations` |
| `oneway_delay_factor = 1.0` applies no conversion (one-way input mode) | `test_oneway_input_not_halved` |
| Missing RTT is interpolated, then fall-backed — never zeroed | `test_missing_rtt_not_zeroed` |
| Fallback RTT must be positive (config validation) | `test_fallback_rtt_must_be_positive` |
| `link_ok` and emulator use identical delay semantics | `test_controller_and_emulator_delay_semantics_match` |
| Reassessment evidence rows exist and are pinned | `test_recorded_rttfix_evidence_referenced` |

## 3. Reassessment results (medium profile, seeds 0–2)

`analysis/delay_semantics_reassessment.csv` (uncalibrated switching)
and `analysis/baseline_results_calibrated.csv` (calibrated): voice
violations/h for `rttfix_threshold_hysteresis` are 80 / 952 / 1 across
seeds 0/1/2. The fix changed absolute violation counts vs the old
halved-RTT-in-reverse treatment; rankings across incumbents were
reassessed and are recorded in the same CSVs.

**Correction to an earlier note:** `analysis/notes.md`'s "~3.0
voice viol/h" figure is legacy scalar-workload output and must not be
cited next to current medium-profile numbers.

## 4. Violation decomposition (spec-mandated)

Produced by `scripts/decompose_sla_violations.py` →
`analysis/sla_violation_decomposition.csv` (129,600 class-steps: 3
factors × 3 seeds × 3,600 steps × 4 classes) and
`analysis/sla_violation_decomposition_summary.csv`. Reference policy:
`ThresholdHysteresis`, calibrated switching, medium profile.

### Headline: violations are congestion-driven, not path-delay-driven

Totals across seeds (all classes) are **identical for
oneway_delay_factor ∈ {0.45, 0.5, 0.55}**: 3,079 violated class-steps
each. All of them sit on the `five_g` underlay (2,845 on seed 1,
225 on seed 0, 3 on seed 2 per factor; ≤3 on `bb`):

| Cause (multi-label) | Violated class-steps (of 3,079) |
| --- | --- |
| `cause_delay_queue` (queueing delay breach) | 3,070 |
| `cause_jitter` | 3,015 |
| `cause_loss_queue` (queue-drop loss breach) | 2,410 |
| `cause_loss_trace` | 9 |
| `cause_outage` | **0** |
| `cause_delay_trace` (one-way path delay alone) | **0** |
| `cause_switch_disruption` | **0** |

Mechanism: the fluid queue's buffer is sized against the underlay's
ceiling capacity (`cap_mbps × queue_buffer_s`, 0.25 s), but trace
capacity can sag to the 20% floor; a backlog that filled at ceiling
rate then drains against 0.2× capacity, producing queue delays up to
1250 ms (= 0.25 s / 0.2) and jitter up to 250 ms — both far above the
voice/video SLA thresholds (150 ms delay, 30/40 ms jitter). Path
one-way delay (mean 20 ms on violated steps, max 68.5 ms) never
breaches an SLA on its own, so ±10% in the one-way factor cannot flip
any step.

**Implication for the RTT fix:** the factor correction is semantically
right and regression-pinned, but it does not change safety behaviour in
the current medium-profile scenarios. Safety risk concentrates in
queue sizing vs capacity sag, not in delay-unit conversion.

### Factor-sensitivity summary

| Factor | Violated class-steps | delay-trace | delay-queue | jitter | loss-queue | loss-trace | outage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.45 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |
| 0.50 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |
| 0.55 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |

## 5. Limitations

1. Decomposition covers seeds 0–2, medium profile, one reference
   incumbent (`ThresholdHysteresis`), calibrated switching. Other
   profiles, regimes and RL policies are out of scope of this audit
   round.
2. Cause flags are multi-label; the table does not partition into
   exclusive causes (delay-queue and jitter co-occur by construction
   since jitter includes 0.2 × queue delay).
3. The 1250 ms queue-delay ceiling is an artefact of buffer sizing
   against ceiling capacity. A capacity-aware buffer sizing is a
   candidate fidelity fix and should be evaluated in cross-engine
   validation, not changed silently now.
4. Asymmetric-path sensitivity (different forward/reverse delay) is
   **not** modelled: all trace RTTs are symmetric round-trip
   measurements, and the release provides no per-direction data. The
   0.5 factor is the standard symmetric approximation; a one-sided
   skew sensitivity analysis would require data the sources do not
   carry.
