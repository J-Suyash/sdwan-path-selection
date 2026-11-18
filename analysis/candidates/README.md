# UNREVIEWED CANDIDATES - evidence tooling, not adopted gates

Everything in this directory is candidate evidence. Nothing here is installed
in any gate, and nothing here may be emitted under an accepted metric name.

## sdwan-band-derivation-v4-candidate.py

Cross-engine band derivation, v4, written 2026-11-18 09:22 IST against branch
revision 127c33d; first executed in the worktree at ~09:24 and re-executed at
bf8c34c (~13:52). Computes half-range q90 (baseline) and true
max-deviation-from-median q90 (sensitivity) for the six bandable metrics from
the raw per-run calibration CSVs.

Inputs (sha256, verified unchanged 2026-11-18):
- testbed/outputs/cal_v1_full/switch_metrics_raw.csv
  ce16264fe95d8b69cce053188f4348938900e4e54e853f45219051a7f7ba5d81
- testbed/outputs/cal_v2_perpath/switch_metrics_raw.csv
  b09cfdf6db81470c8a447fff46af40a2bff1c6bf83a4b39a2c2c5c6bc69e1070

Recorded output: v4-out-20261118.json (first execution). Re-execution
reproduces 48/48 cells and 240 runs; values bit-exact for half the metrics
and within a few ulps (~1e-15 relative, float-op-order level) for the rest.

The committed analysis/cross_engine_thresholds.csv matches the first
execution bit-exact; its legacy column name max_dev_from_median_q90 holds the
half-range values (naming history recorded in
scripts/derive_cross_engine_thresholds.py).

## queue_delay_proxy.py

Flagged candidate estimator for a queue-delay-like quantity from two-point
captures. Emits `queue_delay_proxy_ms` only - never `queue_delay_ms` - and
must not feed any acceptance gate. See the module docstring for the known
negatives and uncertainty bounds.
