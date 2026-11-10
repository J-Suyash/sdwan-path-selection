# Cross-engine validation plan and status

Round item 5. Status: **IN PROGRESS — harness complete, runs pending.**
Nothing here authorises final dataset export.

## Matched conditions (binding for every case)

Both engines must run identical: workload rate/packet size/transport,
path RTT/jitter/capacity (from the same scenario values), queue limits
(per-path packet limits from `switch_calibration_v2.json`), scheduler
(FIFO), and switching condition (same path pair, same route-update
method on the Mininet side; the emulator reproduces the calibrated
transient distribution).

**Emulator queue mapping (matched mode):**
`buffer_bytes = limit_packets × packet_bytes` — i.e. bb 4166×1400,
five_g 3125×1400, leo 2083×1400 bytes. The default emulator buffer
(`cap_mbps × queue_buffer_s`) is *not* the matched configuration and
must not be used for cross-engine cases.

## Cases (`testbed/scenarios/cross_engine_cases.json`)

| Case | Purpose | Stressor |
|---|---|---|
| `ce01_queue_saturation_udp` | buffer fill, overflow drops, queue-delay ceiling | 60 Mbps UDP into sagged five_g capacity |
| `ce02_sla_boundary_voice_udp` | violation decision at the 150 ms / 30 ms voice boundary | leo→five_g, sub-threshold delay + jitter |
| `ce03_sla_boundary_interactive_tcp` | retransmission-based loss near the 5% threshold | TCP interactive |
| `ce04_switch_transient_video_udp` | interruption duration and loss burst | leo→bb highest-RTT contrast |

5 repetitions per case per engine.

## Comparison statistics (distributions and tails, not means)

`scripts/cross_engine_compare.py`: per metric — medians, p95 tail
ratio, KS statistic + p-value, Cliff's delta with effect-size labels.
Regression-tested: identical medians with different tails are flagged
(`test_compare_metric_distributions_not_just_means`).

## Acceptance thresholds (derived, not assumed)

`scripts/derive_cross_engine_thresholds.py` computes the within-engine
reproducibility band from the calibration sweeps' replicate deviations
(per cell: max |replicate − cell median| / 2, aggregated as q90 across
cells). Current bands from `cal_v1_full` (24 cells, ≥4 replicates):

| Metric | Band (q90, absolute) |
|---|---|
| `interruption_s` | 0.0033 s |
| `loss_frac` | 0.0072 |
| `reordering_frac` | 0.0026 |

A metric is accepted when both |median difference| and the p95 tail
deviation fall inside the band. The bands will be recomputed including
the `cal_v2_perpath` replicates before the comparison is judged.

## What remains before the gate can be evaluated

1. `cal_v2_perpath` sweep completion (120 runs, in progress) and
   aggregation under fingerprint `<sha>|per_path_v2`.
2. Emulator matched-mode runs for the four cases (queue mapping above;
   requires a matched-mode `SDWanConfig` — not yet implemented).
3. Mininet runs of the same cases (reuse the v2 runner with the case
   scenario).
4. Comparison with the recomputed bands; a **failure on
   `interruption_s` is expected and informative**: the emulator draws
   interruptions from the calibrated model rather than reproducing
   route-update latency, and the derived band (3.3 ms) is tight. A
   documented failure with cause is a valid round outcome; it must not
   be papered over by widening bands.
5. Owner review; only then an acceptance artefact at
   `data/cross_engine_validation_acceptance.json` with the required
   provenance fields (`REQUIRED_ACCEPTANCE_FIELDS`).
