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

### Rates with explicit denominators (factor 0.5)

Denominators (2026-11-10 round): per (seed, class) — 3,600 class-steps
= one 1-hour episode, so viol/h == viol/class-step-rate; per
(seed, class, underlay) — steps the class actually spent on that
underlay (rate per 1,000 steps there). Artefacts:
`analysis/sla_violation_rates_by_class.csv`,
`analysis/sla_violation_rates_by_underlay.csv`.

| Seed | Class | Viol/h | Rate of class-steps | On five_g (viol / 1,000 steps) | On bb (viol / 1,000 steps) |
|---|---|---|---|---|---|
| 0 | voice | 80 | 2.22% | 79 / 3,596 = 22.0 | 1 / 4 ⚠ |
| 0 | video | 80 | 2.22% | 79 / 3,596 = 22.0 | 1 / 4 ⚠ |
| 0 | interactive | 68 | 1.89% | 67 / 3,596 = 18.6 | 1 / 4 ⚠ |
| 1 | voice | 952 | 26.44% | 951 / 3,596 = 264.5 | 1 / 4 ⚠ |
| 1 | video | 952 | 26.44% | 951 / 3,596 = 264.5 | 1 / 4 ⚠ |
| 1 | interactive | 944 | 26.22% | 943 / 3,596 = 262.2 | 1 / 4 ⚠ |
| 2 | voice | 1 | 0.03% | 0 | 1 / 4 ⚠ |
| 2 | video | 1 | 0.03% | 0 | 1 / 4 ⚠ |
| 2 | interactive | 1 | 0.03% | 0 | 1 / 4 ⚠ |
| all | bulk | 0 | 0% | 0 | 0 |

⚠ The bb rows have a 4-step denominator: they are the single step in
which each class first lands on bb after a switch (transition-instant
accounting), **not** a per-underlay rate. Per-underlay rates are only
meaningful for five_g where residence is long.

**The 861 ms mean is calculated over violated observations only**
(factor 0.5: 3,079 rows, mean 861.06 ms); the mean over *all* rows is
61.6 ms. Verified by `tests/test_sla_decomposition.py::test_committed_decomposition_rates_and_denominators`.

**Diagnostic purity:** `diagnose()` re-calls `_class_qos` on the
already-updated post-step state and restores the counters it perturbs.
Proven by two tests: exact state-snapshot equality after every diagnose
call (`test_diagnose_preserves_env_state_exactly`) and identical
30-step trajectories/violations/cost with and without diagnosis
(`test_diagnose_does_not_diverge_trajectory`). The full 3,079 count is
additionally reproduced end-to-end from raw env transitions
(`test_decomposition_reproduces_violations_from_raw_transitions`).

### Factor-sensitivity summary

| Factor | Violated class-steps | delay-trace | delay-queue | jitter | loss-queue | loss-trace | outage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.45 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |
| 0.50 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |
| 0.55 | 3,079 | 0 | 3,070 | 3,015 | 2,410 | 9 | 0 |

## 5. Queue model fidelity verdict (round item 1)

Traced end-to-end: `FluidQueue.step` (`env/queue.py`) is byte-based
(`Mbps × 1e6/8 × dt`), drains the backlog before admitting new
arrivals, clamps occupancy to a fixed `buffer_bytes`, and conserves
`offered = delivered + dropped + Δoccupancy` exactly
(`tests/test_queue_fidelity.py::test_step_units_and_conservation`).
`SDWanEnv._update_queues` feeds per-underlay offered load and the
trace capacity of the current second; `_class_qos` reports
`occupancy / instantaneous_service_rate` where the service rate is the
**current** step's trace capacity, and the occupancy is the
**end-of-step** snapshot (one-step persistence) —
`test_env_queue_delay_reflects_instantaneous_service_rate`.

**1250 ms ceiling derivation:** buffer_bytes is fixed at
`cap_mbps × 0.25 s` (ceiling-rate service). `traces.py` floors trace
capacity at `0.2 × cap`. A backlog filled at ceiling rate persists at
the buffer limit (overflow drops instead of shrinkage), and the
reported delay against floor-rate service is
`0.25 s / 0.2 = 1.25 s = 1250 ms`. Numerically reproduced and pinned by
`test_queue_delay_ceiling_from_capacity_floor`.

**Fixed vs capacity-varying buffer:** keep the buffer **fixed in
bytes**. Three reasons: (a) the Mininet reference qdisc limit is fixed
in packets — matching engines requires fixed-byte buffers; (b) the
inflation is physically real, not an artefact: a standing backlog at
low service rate genuinely costs that much delay, and hiding it by
shrinking the buffer would just convert delay violations into loss
violations; (c) a capacity-proportional buffer would cap modelled
delay at 0.25 s regardless of conditions, which is an active-management
policy, not a queue model — and it would bias SLA results favourably
without any physical change. Per the round instruction, no parameter
was changed. The genuine modelling caveat (buffer sized against
ceiling capacity while qdisc limits in the v2 testbed round are
per-path packet counts) is handled by the matched-mode mapping in
`docs/cross_engine_validation_plan.md`.

## 6. Limitations

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
