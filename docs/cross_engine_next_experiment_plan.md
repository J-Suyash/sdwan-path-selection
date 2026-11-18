# Cross-engine next experiment plan and criteria

Status: REVIEW DRAFT for the owner, 18 Nov 2026. Prepared under the
owner's judgment delegation ("do what's best for research"); nothing here
is adopted, no runs have executed, and the privileged stage needs scoped
approval before it starts. Companion documents:
docs/cross_engine_validation_scope_recommendation.md (scope
classification, still the reference for what is gated how) and
docs/cross_engine_validation_plan.md (original plan, unchanged).

## 1. Comparable definitions (explicit)

| metric | Mininet runner | fluid emulator | comparability |
| --- | --- | --- | --- |
| loss_frac | 1 - received/sent, packet counts, whole sender log (analyze.py summarize_traffic) | dropped/offered bytes, full episode (queue.py) | quantity-level; equal under each case's constant datagram size |
| throughput_mbps | received x packet_bytes x 8 / arrival span (analyze.py:67-71) | delivered bytes x 8 / episode duration | quantity-level with a documented denominator difference: arrival span vs fixed window; they agree under continuous flow with uniform loss and diverge under tail-heavy loss (span shortens) |
| delay_median_ms | per-packet median over the run | median over per-step aggregate delay (0.5*RTT + occupancy/service drain, sdwan_env.py:243-260) | estimator-level only; band measures estimator deviation, never per-packet equality |
| jitter_mean_ms | mean |delta packet delay| | mean over per-step jitter (0.5*|delta RTT| + 0.2*drain + disruption term, sdwan_env.py:261-270) | estimator-level only; constant-series mode carries zero trace jitter, so runs with non-zero case jitter compare queue/disruption contributions only |
| interruption_s | max inter-arrival gap minus median gap (analyze.py) | calibrated switching-model effect (switching.py) | informative only, never gated; the emulator value derives from the testbed-calibrated model (near-circular as validation) |
| queue_delay_ms | none recorded | none emitted | EXCLUDED until an owner-adopted estimator pair exists; the residence-minus-base candidate stays flagged (28% negatives, causes hypothesized) |
| reordering_frac | per-packet order statistic (analyze.py) | not expressible (no packets) | Mininet-only diagnostic; gate entry OUT-OF-MODEL-SCOPE |

## 2. Capacity and size accounting convention

Observed on the ce01 smoke pcaps (prequeue/postqueue/traffic): wire frame
1442 B for a 1400 B datagram (Ethernet 14 + IP 20 + UDP 8). traffic.py
paces rate_mbps in packet_bytes datagrams (payload rate), while tc
policing accounts L3 bytes (1428 B) and the wire carries 1442 B. The
systematic offset between payload-denominated emulator quantities and the
policed link is therefore about 2.0% (1400/1428) to 2.9% (1400/1442)
depending on accounting layer.

Convention for matched runs: emulator capacity_mbps per path is scaled by
packet_bytes/(packet_bytes+28) = 1400/1428 (tc L3 accounting), and
queue_buffer_bytes stays limit_packets x packet_bytes (packet-count limit
is exact; the byte view is payload-denominated like the fluid flow). Both
the nominal and scaled values are recorded in run_manifest.json. The
matched runs double as the empirical check: loss-onset rates should agree
to within the residual accounting layer difference; if they do not, the
convention is revisited before any band is derived. The 2-3% figure is
below ce01/ce04 effect sizes and matters only near boundary regimes
(ce02), where it is reported, not absorbed silently.

## 3. Quality guards (explicit)

* Fail-closed coverage end to end: incomplete metric coverage exits 2,
  writes emulator_metrics.partial.csv (never the complete name), and the
  comparator refuses any input whose sibling coverage.json reports
  unsupported required metrics.
* interruption_s rows live only in emulator_informative.csv.
* Bands must be derived under THESE definitions from matched runs; the
  within-testbed repeatability rows
  (analysis/cross_engine_thresholds_proposal_draft.csv) quantify
  runner-side spread and do not automatically apply.
* Required metrics come from the original
  testbed/scenarios/cross_engine_cases.json; switching that source after
  scope approval is an explicit code+docs change, never silent.
* All artifacts carry raw_unvalidated labels until the owner adopts the
  scope; no case is excluded without a documented reason (original gate
  prose stands).

## 4. Experiment plan

Stage A (unprivileged, emulator-only): one harness extension first -
extract per-step delay/jitter series so the estimator-level rows exist
(routine plumbing, tested, flagged estimator-level; no gate use). Then
run the harness over the four case drafts (ce01-ce04), 5 repetitions
each at fixed seeds. Produces numeric rows for loss_frac/throughput_mbps
plus estimator-level delay/jitter rows, emulator_informative.csv, and
coverage.json per case. Label: raw_unvalidated_scaffolding.

Stage B (privileged, needs scoped approval): the Mininet matched batch -
the same four drafts, 5 repetitions each, durations per the drafts
(14 s runs plus setup/teardown). Side effects: privileged Mininet with
network namespaces on the laptop; no changes to the user's s1 bridge; no
global mn -c; per-run artifact directories with pcaps, qdisc and backlog
series; run_manifest per run. Approximate wall time and the exact
approval scope are stated in the approval request when this stage is
brought.

Stage C (unprivileged analysis): comparator run over matched pairs,
band derivation under the Section-1 definitions (half-range baseline +
max-deviation sensitivity, per the delegated rule), and a deviation
report. Deviations are reported as findings - including negative ones -
with no gate cherry-picking.

## 5. Criteria the evidence will be judged against (for student review)

* The validation claims platform fidelity only: aggregate traffic
  accounting (loss/throughput) at quantity level, delay/jitter at
  estimator level, under matched constant conditions, across the
  saturation (ce01), boundary (ce02) and switch-transient (ce03/ce04)
  regimes.
* It does not claim per-packet equivalence, packet-order behavior,
  transport fidelity, or SLA-compliance ranking trustworthiness by
  itself; the downstream reproduction claim (Bista Sec IV Table III
  ranking) additionally needs its own seeds/CI discipline, which the
  anchor paper itself lacks.
* Success is a documented map of where the fluid model matches and
  where it deviates, with measured bands - not "all gates green".
