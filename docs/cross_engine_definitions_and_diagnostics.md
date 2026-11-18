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
  seed-invariant (two-seed test,
  tests/test_emulator_matched_run.py::test_matched_mode_metric_determinism_across_seeds:
  seeds 0 and 1 produce bit-identical numeric row values; verified for a
  saturated case, to be extended per case draft when they run).

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

D2 - Throughput window alignment. Decision: the measurement endpoints
for both engines. Recommendation: declare explicit COMMON endpoints -
t0 = first packet sent, t1 = last packet received or a bounded drain
timeout - applied identically to both sides, rather than assuming a
drain tail makes the emulator's fixed window identical to the runner's
first-to-last arrival span. Two details make the structural-equality
claim premature: the first-packet offset (the runner's span starts at
the first arrival, the emulator window at step 0) and the definition
of "queue empty" (a precise rule: occupancy below one packet's bytes
for a declared number of consecutive steps, inside a bounded drain
extension such as 3 x buffer/service, so a pathological case cannot
hang the protocol). The drain tail still shrinks the boundary term,
but the declared endpoints are the definition; any residual denominator
difference is reported, not assumed away. Requires a small harness
extension (zero-load drain phase with the declared termination rule)
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
occupancy/service drain). Recommendation: keep it a candidate; first
characterization is done (docs/cross_engine_e1_estimator_characterization.md):
the weighting and window must be fixed explicitly (full-run medians are
unstable across weightings in transient regimes), and the
residence-minus-base form with base bytes at the departure rate is the
structurally consistent candidate, verified against one regime pair of
one run - consistency, not validation. The candidate
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
Recommendation: the two-seed determinism check is now a standing
test (Section 1); once each case draft passes it, a single emulator rep
per case suffices, and within-engine spread comes from the runner
corpus only. Zero emulator variance is a model property, not evidence of
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
approval; specification for review, not scheduled). Configuration:
single-path topology matching the matched-run build - root tbf rate
50 Mbit, burst 15000 B, latency per the 120/bw formula; netem child
10 ms delay, 0 ms jitter, 0% loss, limit 3125 packets; one UDP
workload of 1400 B datagrams paced at exactly 50.0 Mbps payload for
20 s, then a bounded drain window (capture stops at the earlier of
qdisc backlog 0 or 5 s after the last send). Measurement at three
layers plus counters: sender-side capture, server-side capture, and
receiver application records, with tbf/netem Sent and dropped counters
before and after. The middle 15 s (excluding the first 2 s and the
last 1 s) is the declared steady-state measurement window; the full
span is reported alongside. Predictions for delivered-to-NIC rate and
qdisc-counted loss over that window: wire-size (1442 B) accounting ->
48.54 Mbps and 2.91% loss; L3 (1428 B) -> 49.02 Mbps and 1.96%;
payload accounting -> about 50 Mbps and about 0% loss. Assumptions
behind the predictions: sender pacing precision as observed in the
smoke (monotonic scheduling), no competing traffic, the burst-15000
steady-state behavior seen in the smoke, and zero kernel capture drops
(tcpdump reported 0 at 60 Mbps in the smoke; P1 re-checks and treats
any nonzero kernel drop count as contaminating the run). Known
confounds, from E1: NIC-to-app socket loss reached 1.78 pp in the
smoke, so app-level counts CANNOT discriminate the hypotheses - the
primary basis is server-side capture plus qdisc drop counters, with
app-level counts reported separately; startup transients and
finite-run burst/backlog effects are excluded by the steady-state
window. Inconclusive handling: if capture reports kernel drops, if
qdisc and capture counts disagree beyond packet-boundary granularity,
or if the observed rate/loss matches no prediction within the
pre-registered counting bounds, the run is declared inconclusive -
counters are reported as-is, with no silent rerun or adjustment; the
configuration is revised on the recorded evidence before any new
approval request. Side effects: privileged Mininet with network
namespaces created and destroyed by the run, its own bridge instance
and tc qdiscs on its own veths; the user's s1 bridge is untouched; no
global mn -c; no system settings changed; artifacts under
testbed/outputs/rate-diag-p1/. Duration: 20 s measurement plus
setup/teardown; actual wall time is reported after the fact, not
guaranteed. Decision it settles: D1's residual assumption (the tbf
token-consumption length basis).

## 4. What this unlocks

With D1-D6 settled (E1 and P1 evidence plus owner sign-off on the
definitions), the Stage A emulator runs and the Stage B matched batch
in docs/cross_engine_next_experiment_plan.md become well-defined, and
Stage C's freeze-then-evaluate can proceed on frozen rules. Until then,
no four-case execution and no bands.
