# ce01 smoke one-off diagnostic helpers

Preserved copies of the ad-hoc analysis scripts used on 2026-11-18 against
the single ce01 smoke run at `testbed/outputs/ce01-smoke/` (run e00-r00,
scenario sha f4944ae2e2db1c66, manifest raw_unvalidated). These are
diagnostics, not part of the validated toolchain; every quantity they
print is raw and unvalidated.

Run from the repo root on a machine with the artifacts present.

- `ce01_analyze.py` - backlog sampler vs event epoch, matcher quality flags,
  residence series (median/p95/max).
- `ce01_reconcile.py` - sender/receiver/pcap denominator reconciliation:
  app-missing = pre-tap-only + NIC-to-app gap; scatter analysis of missing
  seqs.
- `ce01_drops.py` - qdisc drop-counter reconciliation from
  backlog-series.log first/last blocks: netem dropped == pre-tap-only
  count exactly; conservation check against sent_frames.
- `ce01_seq_order.py` - capture-sequence inversion analysis with
  extraction validation (timestamp monotonicity, decode set-equality with
  sender.csv, duplicate/wrap checks, divergence vs receiver.csv). Reports
  observed capture order only; no physical-wire or platform-mechanism
  claim.
