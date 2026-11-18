# Cross-engine definitions and diagnostic protocol

Status: REVIEW DRAFT for the owner, 18 Nov 2026. Nothing here is
adopted. This document lists the exact definitions that are fixed, the
ones still open, the decision each one needs, a recommendation with
evidence, and the bounded diagnostics that settle the remaining
empirical unknowns. Companion: docs/cross_engine_next_experiment_plan.md
(stages and guards) and docs/cross_engine_validation_scope_recommendation.md
(metric scope classification).

## 1. Definitions already fixed and verified (evidence on branch)

* loss_frac: runner = 1 - received/sent packet counts over the whole
  sender log (testbed/analyze.py summarize_traffic); emulator =
  dropped/offered bytes over the full episode (env/queue.py). Equal only
  under the three conditions in Section 2, D3.
* throughput_mbps: runner = received x packet_bytes x 8 / arrival span
  (analyze.py:67-71); emulator = delivered bytes x 8 / episode window.
* Delay units: testbed netem delay is one-way on a single link; the
  emulator constant series carries rtt_ms = 2 x one_way_delay_ms.
* Queue limit: netem limit is in packets; matched buffer bytes =
  limit_packets x packet_bytes (exact in packet count).
* Size accounting at the policed layer: 1442 B per 1400 B datagram,
  verified from qdisc counters (tbf Sent 45,249,960/31,380 = 1442.0;
  netem Sent 80,186,736/55,608 = 1442.0; backlog 289,842/201 = 1442.0;
  testbed/outputs/ce01-smoke/e00-r00/qdisc_before.txt, qdisc_after.txt).
  No overhead/linklayer parameters are installed (grep over testbed/).
* Emulator determinism in matched mode: under constant_series +
  fixed_load_mbps, every metric input is pinned; RNG touches only
  observation features (episode_start_hour) and workload snapshot info
  fields (env/sdwan_env.py:44, env/workload.py). Numeric outputs are
  seed-invariant (code inspection; confirmed empirically as part of the
  Stage A protocol below).

## 2. Open definitions, the decision each needs, and recommendations

D1 - Capacity scale convention. Decision: whether matched runs scale
emulator capacity by 1400/1442 = 0.970874. Recommendation: adopt the
scale; the 1442 B/packet accounting is counter-verified, and the only
residual assumption (tbf token consumption uses the same per-packet
length as bstats) is settled directly by diagnostic P1 below. Until
adopted, the harness records the convention with applied=false and runs
at nominal capacity. Blocking: yes for interpreting any matched number
near a capacity boundary (ce02); the 2.91% offset is below ce01/ce04
effect sizes.

D2 - Throughput window alignment. Decision: how the emulator window is
defined so its denominator matches the runner's arrival span.
Recommendation: drain-tail protocol - the send phase ends at the case
duration on both sides and measurement continues until queues empty
(the fluid queue drains deterministically; the runner's capture already
extends to the last received packet). Both sides then share the
denominator (last activity minus first activity). This removes the
arrival-span vs fixed-window divergence structurally instead of by
tolerance. Requires a small harness extension (zero-load drain phase)
and a drain tail in the case drafts. Blocking: yes for throughput and
loss rows in any case with tail loss.

D3 - Loss boundary handling. Decision: how bytes still queued at run
end are treated. Recommendation: with the D2 drain tail the residual
goes to zero by construction; until the drain tail exists, the harness
already reports end_residual_occupancy_bytes per run as the boundary
term and no loss equivalence is claimed while it is non-negligible.
Blocking: resolved by D2; reported term already implemented.

D4 - Delay estimator mapping. Decision: whether delay_median_ms is
defined as the median over per-step aggregates (0.5 x RTT +
occupancy/service drain). Recommendation: keep it a candidate until its
systematic offset against the runner's per-packet median is quantified
by diagnostic E1 below (existing data, unprivileged). The candidate
extraction already lands in emulator_estimator.csv with quality
estimator_candidate_unvalidated; it is never gate evidence. Blocking:
yes for any delay row; the estimator-level classification in the scope
recommendation depends on E1's measured offset being understood, not
assumed.

D5 - Jitter in constant-series mode. Decision: whether jitter_mean_ms
participates at all in the matched stage. Recommendation: defer it
(documented limitation), because constant series carry zero trace
jitter and injecting synthetic jitter would invent model behavior the
testbed does not impose. The candidate per-step rows are still
extracted for information. Blocking: no, if deferred explicitly;
silent exclusion is what would block.

D6 - Repetition protocol. Decision: how many emulator repetitions.
Recommendation: run 2 seeds once and assert bit-identical numeric rows
(determinism check per Section 1); afterwards a single emulator rep per
case suffices, and within-engine spread comes from the runner corpus
only. Zero emulator variance is a model property, not evidence of
stability - the protocol must not present it as such. Blocking: no;
protocol clarity for the student review.

D7 - queue_delay_ms and reordering_frac. Unchanged from the scope
recommendation: excluded (no adopted estimator pair; candidate proxy
stays flagged at 28% negatives) and Mininet-only diagnostic with an
explicit out-of-model-scope gate entry. Blocking: no.

## 3. Diagnostics

E1 - Estimator form check on existing smoke data (unprivileged, no new
runs). The ce01 smoke already contains per-packet delays
(traffic.pcap, 55,608 packets) and a qdisc backlog series
(backlog-series.log). Compute the per-step aggregate form
(0.5 x configured RTT + backlog/service rate, in the harness's decision
grid) directly from the measured backlog series, and compare its
median against the measured per-packet median delay. This tests the
estimator MAPPING (D4) against real queue dynamics with zero new
execution. Output: measured offset and its stability across the
pre-sag and post-sag regimes, reported as characterization - never used
to tune the estimator to match. Duration: analysis only, no privilege.

P1 - Capacity accounting rate diagnostic (privileged; needs scoped
approval). One path, no switch or capacity events: constant UDP stream
of 1400 B datagrams offered at exactly the nominal path rate
(50.0 Mbps payload) for 20 s. The three candidate accountings predict
cleanly separated outcomes: wire-size (1442 B) accounting -> delivered
48.54 Mbps payload, loss_frac 2.91%; L3 (1428 B) -> 49.02 Mbps, loss
1.96%; payload accounting -> about 50 Mbps, loss about 0. With about
89,000 packets the counting precision is better than 0.01%, so one run
discriminates. Exact scope: single topology build with one path, one
workload, no events; ~20 s measurement plus roughly 60-90 s setup and
teardown (under 3 minutes total). Side effects: privileged Mininet
with network namespaces created and destroyed by the run, its own
bridge instance and tc qdiscs on its own veth interfaces; the user's
s1 bridge is untouched; no global mn -c; no system settings changed;
artifacts under testbed/outputs/rate-diag-p1/. Decision it settles:
D1 definitively (the tbf token-consumption length basis), removing the
last assumption in the capacity convention before any matched run is
interpreted.

## 4. What this unlocks

With D1-D6 settled (E1 and P1 evidence plus owner sign-off on the
definitions), the Stage A emulator runs and the Stage B matched batch
in docs/cross_engine_next_experiment_plan.md become well-defined, and
Stage C's freeze-then-evaluate can proceed on frozen rules. Until then,
no four-case execution and no bands.
