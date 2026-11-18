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
| loss_frac | 1 - received/sent, packet counts, whole sender log (analyze.py summarize_traffic) | dropped/offered bytes, full episode (queue.py) | quantity-level only under three stated conditions: (i) constant datagram size per case (holds: 1400 B), (ii) aligned comparison window (full-run on both sides), (iii) explicit boundary handling - bytes still queued at episode end are counted by the emulator as neither delivered nor dropped, while the runner sees them as sent-but-not-received until they drain; residual end-of-run occupancy is reported per run in run_manifest.json as a boundary term, and equivalence is claimed only when that term is negligible or excluded |
| throughput_mbps | received x packet_bytes x 8 / arrival span (analyze.py:67-71) | delivered bytes x 8 / episode duration | quantity-level with a documented denominator difference: arrival span vs fixed window; they agree under continuous flow with uniform loss and diverge under tail-heavy loss (span shortens) |
| delay_median_ms | per-packet median over the run | median over per-step aggregate delay (0.5*RTT + occupancy/service drain, sdwan_env.py:243-260) | estimator-level only; band measures estimator deviation, never per-packet equality |
| jitter_mean_ms | mean |delta packet delay| | mean over per-step jitter (0.5*|delta RTT| + 0.2*drain + disruption term, sdwan_env.py:261-270) | estimator-level only; constant-series mode carries zero trace jitter, so runs with non-zero case jitter compare queue/disruption contributions only |
| interruption_s | max inter-arrival gap minus median gap (analyze.py) | calibrated switching-model effect (switching.py) | informative only, never gated; the emulator value derives from the testbed-calibrated model (near-circular as validation) |
| queue_delay_ms | none recorded | none emitted | EXCLUDED until an owner-adopted estimator pair exists; the residence-minus-base candidate stays flagged (28% negatives, causes hypothesized) |
| reordering_frac | per-packet order statistic (analyze.py) | not expressible (no packets) | Mininet-only diagnostic; gate entry OUT-OF-MODEL-SCOPE |

## 2. Capacity and size accounting convention

Verified on this setup's actual qdisc counters
(testbed/outputs/ce01-smoke/e00-r00/qdisc_before.txt and
qdisc_after.txt): the installed qdiscs account 1442 B per 1400 B
datagram - tbf Sent 45,249,960 B / 31,380 pkt = 1442.0 exactly, netem
Sent 80,186,736 B / 55,608 pkt = 1442.0 exactly, backlog 289,842 B /
201 p = 1442.0 exactly. The pcap wire frame (orig_len 1442) matches.
The installed chain is a root tbf (rate, burst 15000, latency 120/bw ms
formula, mirroring mininet/link.py bwCmds) with a netem child
(delay/jitter/loss, limit in packets); no overhead or linklayer
parameters are set anywhere under testbed/ (grep verified). Byte
accounting at the policed layer is therefore Ethernet-inclusive wire
size on this setup - an earlier guess of L3-only (1428 B) accounting was
checked against these counters and is wrong here. Payload fraction at
the policed layer: 1400/1442 = 0.970874, i.e. a 2.91% offset from
nominal. The mechanism (L2 forwarding presenting full frames at the
egress qdisc) is a hypothesis; the counters are the fact.

Convention for matched runs: emulator capacity_mbps per path is scaled
by packet_bytes/1442 = 1400/1442, and queue_buffer_bytes stays
limit_packets x packet_bytes (the packet-count limit is exact; the byte
view is payload-denominated like the fluid flow). Nominal and scaled
values are both recorded in run_manifest.json. Residual uncertainty,
stated not hidden: tbf token consumption is assumed to use the same
per-packet length as the bstats counters (consistent evidence; no
separate rate-precision diagnostic has been run). If the owner wants
that definitive, a small scoped rate diagnostic can be added to the
Stage B approval request. The matched runs double as the empirical
check: loss-onset rates should agree to within this documented
convention; if they do not, the convention is revisited before any band
is derived. The 2.91% figure is below ce01/ce04 effect sizes and matters
only near boundary regimes (ce02), where it is reported, not absorbed.

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

Stage C (unprivileged analysis), freeze-then-evaluate: two separated
phases. Calibration phase (within-engine only): runner-side
repeatability spread from the raw corpus and emulator-side seed spread
from Stage A repetitions, plus an explicit estimator-uncertainty budget
for the estimator-level rows. Comparison rules and bands are derived
from these within-engine sources alone and are FROZEN before any
cross-engine evaluation. Evaluation phase (held-out): matched
cross-engine discrepancies are computed on runs that played no part in
setting the bands and are compared against the frozen bands. A
discrepancy beyond its band is reported as a finding - the bands are
never widened to absorb it. If evidence later shows a band was wrong,
that is a documented revision cycle with a fresh held-out evaluation,
not in-place fitting. Deviations are reported including negative ones,
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
* Rules and bands are frozen before evaluation; tolerances are never
  fitted to the discrepancies they judge.
