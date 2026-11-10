# Switching calibration report

Deliverable for verification spec section 4. Status: **PASS for the
measured sweeps and aggregation** — v1 (shared 1000-pkt, 120/120, 24/25
cells usable) and **v2 (per-path limits, 2026-11-10, 120/120, 24/24
cells usable)**. Both versions are retained separately under distinct
configuration fingerprints and are never aggregated together.

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

## V2 round: per-path queue limits (2026-11-10)

- Scenario `testbed/scenarios/switch_calibration_v2.json`: identical
  events/workloads/transports/repetitions to v1; per-path packet limits
  active from the start (bb 4166 / five_g 3125 / leo 2083 × 1400 B
  packets). Committed at revision `2e2e2cd` **before** the sweep; the
  manifest records git commit `723d133` (the revision that aggregated).
- **Measurement fix applied before the round:**
  `run_switch_calibration.py` normalized `queue_occupancy_frac` by the
  shared 1000-pkt limit and a fixed 1500 B; it now uses
  `queue_limit_for(old_path) × workload.packet_bytes`. v1 raw evidence
  keeps its original values (immutable record).
- Manifest `data/switching_calibration_manifest_v2.json`:
  fingerprint `2c45fb7828fe9337|per_path_v2`, expected=observed=120,
  no missing runs, `e00-r02` mechanically trimmed (sent 643 vs 939
  frames, −31.5% > 20% rule; retained in raw evidence).
- Aggregation: **24/24 cells usable** (23 at 5 reps, 1 trimmed at 4) —
  the v1 NaN-occupancy cell is resolved because occupancy is now
  measured against the correct buffer. 119 rows in
  `data/switching_calibration_v2.csv`.
- Repeatability: interruption CV median 0.039, p90 0.334; measured
  switch-instant backlogs are small (max 4.2% of buffer) so the
  occupancy bucket is degenerate at `empty` — an observation about the
  scenario's operating point, not a defect.
- **Flagged for the owner, not trimmed:** `e00-r00` (voice bb→five_g
  UDP) recorded a 1.86 s interruption while sent_frames was nominal —
  an order-of-magnitude outlier against its 0.002 s siblings. The
  trim rule is defined on sent_frames only; trimming interruption
  outliers without a pre-registered rule would be post-hoc, so the
  run is kept and the cell mean (0.466 s) is known-inflated. Median
  interruption for that cell remains ~2 ms.
- Measured interruption range across the round: 0.8 ms – 466 ms.

## Caveats (binding)

1. **Queue-config consistency.** All 120 v1 runs used the shared
   1000-packet limit (fingerprint `3d6d9c6dc5c22f48|shared_1000pkt`);
   all 120 v2 runs used per-path limits
   (`2c45fb7828fe9337|per_path_v2`). The two versions live in separate
   artefacts (`data/switching_calibration.csv` vs
   `data/switching_calibration_v2.csv`, separate manifests) and are
   never merged; cross-engine validation cases use **v2**.
2. **Five repetitions is a floor, not a target.** It supports the
   ≥3-repeat sufficiency gate and CV estimation, but tail quantities
   (p95 interruption) rest on 4–5 samples per cell. The repeat count
   should be raised for cells feeding safety-relevant thresholds.
3. The stall trims (`e22-r03` in v1, `e00-r02` in v2) show the sweep
   can produce pathological runs; the trim rule (>20% deviation of
   sent_frames from the group median) is documented and applied
   mechanically. There is **no pre-registered rule for interruption
   outliers**; the flagged `e00-r00` case must be resolved by the
   owner (trim, keep, or re-run) before the affected cell feeds
   safety thresholds.

## Traceability

`data/switching_calibration_manifest.json` records: config
fingerprint, git commit, scenario sha256, queue limits, branch
profile/regime, transports, directed transitions, expected/observed
runs, missing runs, excluded runs, and a per-aggregate-row mapping to
raw run IDs (`aggregate_traceability`).
`tests/test_switching_matrix.py::test_raw_runs_trace_to_aggregate_rows`
asserts every raw run is either traced to an aggregate or explicitly
excluded.
