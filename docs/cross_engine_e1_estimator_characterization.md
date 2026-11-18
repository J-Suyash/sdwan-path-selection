# E1 - estimator form characterization on the ce01 smoke (existing data)

Status: characterization record, 18 Nov 2026. Analysis of EXISTING
artifacts only (testbed/outputs/ce01-smoke/e00-r00/); no new runs, no
estimator adopted, nothing tuned to make values agree. Script:
analysis/candidates/e1_estimator_check.py (this branch). Every form
below is a candidate; the per-packet record is the measurement.

Data and pipeline check. prequeue.pcap (sender-side tap, 75,001
packets) and traffic.pcap (server-side tap, 55,608) share the wall
clock with backlog-series.log (159 tc -s samples, mean dt 0.108 s,
min 0.105 / max 0.121), so no cross-clock alignment was estimated.
Per-packet delay = receive minus send epoch joined on the wire sequence
number (traffic.py HEADER "!Qd", readable inside the 128 B snaplen).
Pipeline validation: parsed full-run per-packet median 38.291574 ms
(n=55,608) vs metrics.json delay_median_ms 38.317078 ms (n=54,273, app
basis). The bases differ: see the socket-loss finding below.

Backlog semantics (verified, not assumed). The tbf "backlog" line and
the netem "backlog" line carry IDENTICAL values in every inspected
sample (e.g. 4,504,808 B / 3,124 p on both at epoch 1794987420.189) -
the child netem occupancy propagates into the parent tbf stats. The
observable occupancy is therefore the netem qdisc's: delay line plus
queued excess. Summing the two lines (a naive reading) double-counts.
Post-sag the queue sits pinned at the packet limit (3,124-3,125 of
3,125; 3,125 x 1442 = 4,506,250 B, the earlier limit observation).

Double-counting the base delay - quantified. Candidate form
B = 0.5 x RTT + backlog/service uses the raw backlog, which includes
the delay-line bytes (base_delay x departure rate). Measured effect:
pre-sag form B = 52.96 ms vs per-packet median 37.522 ms (+15.4 ms,
the delay line at 60 Mbps: ~281 KB); post-sag form B = 1239.17 ms vs
1201.269 ms (+37.9 ms, the delay line at 30 Mbps: ~141 KB). Form A
(summing both backlog lines) is worse again (+30.9 ms pre-sag). The
overestimate equals one base delay's worth of bytes, exactly the
double-count this characterization set out to test.

Candidate form D (residence-minus-base, base bytes at the DEPARTURE
rate): 0.5 x RTT + (backlog - departure_rate x base_delay)/service.
Pre-sag: 37.5 ms (exact by construction once the delay line is
removed). Post-sag: 1201.0 ms vs measured 1201.269 ms (-0.3 ms).
This form was selected a priori from the double-counting argument, not
fitted; agreement on one regime pair of one run is a consistency check,
not validation. It remains a candidate, consistent with the previously
flagged residence-minus-base proxy direction; held-out matched runs
decide.

Packet weighting vs time weighting - the largest effect found. Full
run (transient): per-packet median 38.292 ms vs time-weighted median of
the per-step candidate form 747-2,138 ms depending on grid phase. The
two medians answer different questions once a sag splits the run (57%
of packets were sent pre-sag). In steady windows both weightings agree
to <0.1 ms (pre-sag: 52.96/52.96; post-sag 5 s: 1239.17/1239.17).
During the post-sag ramp (2 s window), time-weighted medians move with
the 1 s grid phase from 596 to 1,045 ms while the packet-weighted value
is 851 ms. Consequence for D4: an estimator-level delay comparison must
fix the weighting AND the window explicitly; full-run medians over
transient cases are unstable under both and should not be compared as
headline rows. Steady-state windows with declared weighting are the
defensible comparison unit.

NIC-to-app component (measurement path, mechanism UNVERIFIED). tcpdump
captured all 75,001 sent and 55,608 server-NIC packets with 0 kernel
drops, but the receiver app recorded 54,273. The 1,335 packets present
at the NIC but absent from the app record contribute 1.78 pp of the
runner's 27.637% loss_frac; the qdisc counted 19,393 drops (25.86%).
The mechanism is not established: candidate causes include socket
receive-path loss and early receiver exit at its idle timeout while
tail packets were still queued (the queue held up to ~2.4 s of delay).
Runner loss therefore includes a component the fluid model does not
represent, whatever its cause. Consequences: (i) matched loss comparisons
should use capture-level and qdisc-counter counts, with the app-level
count kept as a reported separate basis; (ii) P1 (rate diagnostic)
must not rely on app-level counts - the observed 1.78 pp NIC-to-app
effect (mechanism unverified) would swamp the 0.95 pp separation
between the 1428 and 1442 hypotheses.

What E1 settles and what it does not. It quantifies the candidate
aggregate forms' structural behavior on real queue dynamics and fixes
the measurement-path facts above. It does not validate any estimator,
and no offset measured here was used to adjust any estimator or
threshold.
