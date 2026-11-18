# Cross-engine decision brief: metric observability on both engines

Status: decision evidence for the owner, grounded in current code
(2026-11-18, branch instinct/reproducibility-diagnostics). Nothing here is
adopted. This brief separates harness plumbing (engineering) from model
limitation (research decisions that are the owner's to make).

## 1. Per-metric observability, as coded

| Metric | Mininet runner definition (source) | Emulator observable (source) | Comparison status |
| --- | --- | --- | --- |
| loss_frac | app-log missing / sent frames (testbed/traffic.py sender/receiver logs; smoke showed this includes a NIC-to-app component: 20,728 missing = 19,393 netem drops + 1,335 NIC-to-app) | dropped/offered fluid bytes per step, aggregated (env/queue.py QueueStep) | Both emit a number; definitions differ (app-loss incl. receive-path gap vs queue-drop fluid bytes). Mapping decision needed. |
| interruption_s | measured around the route update (runner switch path) | calibrated value applied at switch (env/sdwan_env.py:136 `disrupt_until`; env/switching.py loads measured rows) | Emulator value is the calibrated input, not an emergent measurement. The validation plan already expects this comparison to fail and calls the failure informative. |
| reordering_frac | fraction of app-log arrivals with seq below max-seen (runner metric) | NOT AN OUTPUT. reordering_frac exists emulator-side only as a calibrated switch-effect input folded into jitter (env/sdwan_env.py:270) | Unsupported as a cross-engine metric. ce03 and ce04 list it. Owner decision required. |
| delay_median_ms | per-packet one-way delay median from app logs | per-underlay window mean/p95 RTT aggregates (env observation vector) | Different quantity (window RTT aggregate vs per-packet OWD median). Definitional mapping does not exist. |
| jitter_mean_ms | per-packet inter-arrival deviation mean | window jitter aggregate | Same definitional gap as delay_median_ms. |
| throughput_mbps | received bytes / active time | delivered_bytes / time (env/queue.py) | Extractable both sides; window alignment needed. |
| queue_delay_ms | NOT RECORDED anywhere by the runner | not recorded; fluid occupancy_bytes tracked (env/queue.py) | Unsupported on both engines. A flagged Mininet-side candidate proxy now exists (analysis/candidates/queue_delay_proxy.py, emits queue_delay_proxy_ms only). No emulator equivalence established. |

## 2. Unsupported required metrics

- queue_delay_ms (ce01): neither engine records it. Candidate Mininet proxy
  exists with documented negatives (delay-line/backlog sharing can understate
  wait in saturation; residence includes jitter/OVS/tap placement; the 0.6 ms
  drain agreement was total-drain vs residence, not validation).
- reordering_frac (ce03, ce04): unobservable emulator-side without changing
  the emulator's fluid model.

## 3. Feasible routes and what each changes

Route A - harness + explicit metric decisions (recommended for review).
Build the matched-run harness (fixed path conditions, scripted switch,
case workloads, per-run row emission) for the metrics both engines can
express with owner-reviewed mappings (loss_frac, throughput_mbps,
interruption_s with its expected informative failure). Owner separately
decides reordering_frac (drop from the cross-engine gate with documented
cause, or define what emulator quantity, if any, stands for it) and
queue_delay_ms (adopt/reject/extend the flagged proxy after its uncertainty
is quantified on saturated and unsaturated runs).
Changes: engineering harness plus explicit per-metric decisions; no change
to either engine's model.

Route B - packet-level emulator queue. Give the emulator per-packet
observability so reordering and per-packet delay exist natively.
Changes: this replaces the emulator's fifo-fluid core - a research-model
redesign, not engineering. Not started autonomously; needs explicit owner
direction.

Route C - shrink case metric sets to the observable intersection.
Changes: reduces the scientific scope of ce01/ce03/ce04; the quietest
option and the most expensive in intent. Recorded for completeness, not
recommended without owner direction.

## 4. Minor: gate-prose correction (proposed, consistent with current code)

cross_engine_cases.json prose gates on a p95 tail RATIO;
scripts/cross_engine_compare.py gates the ABSOLUTE p95 deviation
(|p95_emu - p95_mini| <= band) and only reports the ratio. The band is
unit-bearing, so a dimensionless ratio gate is incoherent. Proposal: edit
the cases.json prose to match the code. No gate behavior changes.
