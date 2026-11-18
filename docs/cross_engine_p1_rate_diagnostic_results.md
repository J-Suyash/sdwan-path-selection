# P1 rate-accounting diagnostic - results record

Status: executed once (approved single scoped run, user approval 18 Nov
2026 15:13 IST via WhatsApp), artifacts preserved under
testbed/outputs/rate-diag-p1/ (scenario sha256
c9d705de0791eae99b791ecc042e0630ef8730cea4ad6afc707c47b3fc172325,
dry-run plan recorded before execution). Label: raw_unvalidated
diagnostic evidence. The rate-based discriminators below were adopted
AFTER observing zero qdisc drops - they are exploratory evidence, not
prespecified confirmation.

## Provenance

- A first launch attempt failed at sudo authentication before any
  Mininet object was created (fingerprint-prompt timeout raced the
  credential-file cleanup). Zero state was verified before the actual
  launch (0 network namespaces, 0 veth links). The diagnostic itself
  ran exactly once. No credential details are recorded here; the
  credential was transferred encrypted, never printed or logged, files
  shredded after use, sudo timestamp revoked after the run.
- Execution: RUN_EXIT=0. Post-run cleanup verified: no leftover
  namespaces or veth links, the user's s1 bridge present and DOWN as
  before (untouched), no global cleanup performed.

## Configuration (as approved)

Single workload over one shaped path: UDP, 1400 B datagrams, 50.0 Mbps
payload for 20 s; tbf 50 Mbit (burst 15000 B, latency 2.4 ms) + netem
child (10 ms delay, 0 jitter, 0% loss, limit 3125 packets); captures at
sender NIC, branch post-queue, and server NIC; qdisc counters and a
~10 Hz backlog series (209 samples, mean dt 0.1105 s); receiver app
records kept as a separate basis. The scenario's no-op capacity event
(50 -> 50 at warmup t=2 s) is a routing anchor required by the runner
and does not change the rate.

## Measurements

- Sent: 89,287 packets; all three captures report 89,287 with 0 kernel
  drops. Receiver app recorded 87,273 (2,013 NIC-to-app missing,
  mechanism unverified - same measurement-path caveat as E1).
- qdisc Sent 128,751,854 B / 89,287 pkt = 1442.0 B/packet exactly
  (prespecified counter verification: bstats accounts wire size).
- qdisc dropped 0. The prespecified LOSS discriminator did not
  separate the hypotheses: the netem child buffer (limit 3125 packets)
  absorbs the ~2-3% excess, which stays below the limit. Loss is 0
  under all three accountings here.

## Exploratory rate analysis (post-observation discriminators)

- qdisc Sent-counter slope over the saturated window (service rate in
  accounted bytes): measured 6,250,521 B/s (least-squares over n=176
  samples, residual sd 8,140 B; residuals are autocorrelated, so no
  independent-replicate uncertainty is claimed). Predictions:
  wire-length tokens 6,250,000; L3-length tokens 6,309,000;
  payload-length tokens 6,438,000 B/s. Measured agrees with wire-length
  to 0.008% and sits 58,500 B/s from the L3 alternative - descriptive
  agreement, not a significance claim.
- Backlog growth slope, same window: measured 187,198 B/s (residual
  sd 3,415 B). Predictions: wire 187,600; L3 128,600; payload ~0 B/s.
  Agrees with wire within 0.2% and sits ~59,000 B/s from the L3
  alternative - again descriptive agreement.
- Corroboration: peak backlog 3,785,250 B (2,625 packets, vs ~2,600
  predicted under wire accounting) at t=20.64 s, then drained in
  ~0.61 s after send stop. Startup region flat at 0 backlog.
- App-basis delay: median 301 ms, p95 565 ms, max 594 ms - the backlog
  ramp is visible in delay, consistent with a growing queue at ~3%
  overload, not with a no-overload accounting.

## Bounded conclusion

On this setup, tbf accounts and polices at 1442 B per 1400 B datagram
(Ethernet-inclusive wire size): counter-exact at the byte/packet ratio
and descriptively matched by the service-rate slope and backlog-growth
slope (0.008% and 0.2% from the wire-accounting predictions; the
nearest alternative is tens of KB/s away on both). The D1 residual assumption (token
consumption length basis) has direct rate evidence for wire-size
accounting. Caveat carried honestly: the rate-based discriminators were
adopted after observing zero drops (exploratory, not prespecified);
the owner decides whether this evidence suffices to adopt the 1400/1442
capacity convention, or wants a prespecified confirmation designed
upfront (would need a new scoped approval; none is requested now).
