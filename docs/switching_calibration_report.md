# Switching calibration report

Deliverable for verification spec section 4. Status: **PASS for the
measured sweep and aggregation** (120/120 runs, 24/25 cells usable);
two documented caveats bound how the rows may be used.

## What was run

- Scenario: `testbed/scenarios/switch_calibration_v1.json` — 24 events
  covering all 6 directed path transitions (bb↔five_g, bb↔leo,
  five_g↔leo), 4 workloads (voice, video, interactive, bulk), UDP and
  TCP transports, 5 repetitions each = 120 Mininet runs.
- Queue configuration **as run**: shared 1000-packet limit
  (`queue_limit_packets: 1000`). Per-path limits were added to the
  scenario file *after* the sweep started; the manifest is therefore
  built from the committed as-run snapshot
  `testbed/outputs/cal_v1_full/scenario_as_run.json` (sha256 pinned in
  `data/switching_calibration_manifest.json`), not from the edited
  HEAD scenario. Test: `tests/test_switching_matrix.py::test_as_run_scenario_snapshot_differs_from_head`.
- Route update method: `ovs-ofctl-openflow13-mod-flows`.
- Raw evidence committed: per-run `metrics.json`, qdisc before/after
  dumps, `tcpdump.log`, plus `switch_metrics_raw.csv`
  (32 columns/run). Packet captures and per-second sender/receiver
  series remain on disk only (`testbed/outputs/cal_v1_full/`, 237 MB).

## Expected vs observed

| Quantity | Expected | Observed |
| --- | --- | --- |
| Events × repetitions | 24 × 5 = 120 | 120 (`missing_runs: []`) |
| Directed transitions | 6 | 6 |
| Transports | udp, tcp | udp, tcp |
| Unique run keys | 120 | 120 (no duplicates) |
| Stalled runs | 0 tolerated | 1 (`e22-r03`: sent 2,047 frames vs 5,835 nominal, interruption 80.85 s) — **excluded with documented reason**, retained in raw evidence |

## Aggregation and sufficiency

`scripts/build_switch_calibration.py` buckets runs by
(old/new RTT, jitter, flow type, transport, in-flight, occupancy) and
requires ≥3 valid repetitions:

- **23 cells usable (5 reps), 1 trimmed_usable (4 reps after stall
  trim), 1 insufficient (1 rep, NaN occupancy: bulk/tcp/huge).**
- The insufficient cell is excluded from `data/switching_calibration.csv`
  (119 model-ready rows loaded by `SwitchingModel`;
  `configs/config.yaml` points `switching_calibration_path` at it).

## Repeatability (5 repetitions per cell)

| Metric | Median CV | p90 CV | Max CV |
| --- | --- | --- | --- |
| Interruption duration | 0.016 | 0.104 | 0.842 |
| Loss fraction | 0.000 | — | 1.21 |
| Reordering fraction | 0.000 | — | 2.24 |

Interruption timing is highly repeatable (median CV 1.6%); loss and
reordering are bursty (many zero-loss cells with occasional large CVs
in low-loss cells, where small absolute variation dominates).

Measured interruption durations span **0.7 ms – 182 ms** and loss
fractions 0 – 5.9% per cell — all sub-second relative to the 1 s
decision interval, which is why the emulator prorates transients per
decision step (`disrupted_frac`) instead of applying a binary
whole-step rupture (regression-tested in
`tests/test_model_invariants.py::test_sub_second_switching_fractional_transients_are_prorated`).

## Caveats (binding)

1. **Queue-config consistency.** All 120 runs used the shared
   1000-packet limit. Rows calibrated under this configuration are
   fingerprinted `3d6d9c6dc5c22f48|shared_1000pkt` and must not be
   merged with future per-path-limit rows
   (`config_fingerprint` partitions them;
   `test_incompatible_configs_not_aggregated`). Cross-engine validation
   scenarios that use per-path limits require a new sweep round.
2. **Five repetitions is a floor, not a target.** It supports the
   ≥3-repeat sufficiency gate and CV estimation, but tail quantities
   (p95 interruption) rest on 4–5 samples per cell. The repeat count
   should be raised for cells feeding safety-relevant thresholds.
3. The single stalled run shows the sweep can produce pathological
   runs; the trim rule (>20% deviation of sent_frames from the group
   median) is documented and applied mechanically, but with only one
   occurrence its false-positive rate is unestimated.

## Traceability

`data/switching_calibration_manifest.json` records: config
fingerprint, git commit, scenario sha256, queue limits, branch
profile/regime, transports, directed transitions, expected/observed
runs, missing runs, excluded runs, and a per-aggregate-row mapping to
raw run IDs (`aggregate_traceability`).
`tests/test_switching_matrix.py::test_raw_runs_trace_to_aggregate_rows`
asserts every raw run is either traced to an aggregate or explicitly
excluded.
