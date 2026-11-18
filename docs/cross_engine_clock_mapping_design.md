# Frozen clock-mapping design for timing-expanded support runs

18 November 2026. Proposal for review and frozen interpretation only. No implementation, traffic, tuning or acceptance rule is included. This design exists because the eventual matched comparison should include NIC-side rate/timing as well as counter loss. A five-run batch without this would predictably lack that evidence and invite recollection.

## Existing evidence that constrains the design

The approved single ce01 support run already contains one host's epoch and monotonic timestamps for every sender-side packet in `prequeue.pcap` sequence payloads. A read-only check found first-packet `epoch - monotonic = 1794782505.6093206` and last-packet offset `1794782505.6092703`, a drift of -5.0176604418084025e-05s over about14s. This is evidence from one existing run that the same-host clocks are aligned closely enough for this intended mapping. It is not a general timing guarantee, and it does not justify retroactively inferring other runs' app receive times.

## Frozen definition

For a future timing-expanded run only, define a run-local clock mapping using explicit same-process marker pairs:

- Before traffic starts, the runner records a marker with one `time.time()` value and one `time.monotonic()` value, written atomically to the run directory.
- After traffic/drain and before captures/receivers are terminated, it records a second pair.
- Every relevant capture packet already carries sender monotonic time in its payload and epoch time at its capture frame. The endpoint mapping remains packet-specific: `estimated_epoch = captured_offset_from_sender_epoch + sender_monotonic_s`, where `captured_offset_from_sender_epoch` is calculated from that packet's own observed pair at the sender tap when available. For post-queue/server captures whose payloads carry the same sender monotonic value, use the run-local marker-pair affine relation, not the sender tap's per-packet offset.
- The affine mapping is offset plus drift from the two marker pairs, fit exactly through the pair. No regression, smoothing or tolerance is fitted to packet outcomes. Marker residuals and per-packet sender-tap offset spread are reported.
- The mapped endpoint is not silently substituted for the explicit monotonic matched endpoint. Both are recorded. A NIC matched-window count/rate is defined by counting capture frames whose estimated epoch is within the mapped application endpoint and whose packet sequence was sent within [t0,t1]. It is labeled `mapped_capture_matched_window`, never raw application delivery.
- Qdisc counters remain full-drained-run counters; capture-based window metrics are descriptive, not a replacement for qdisc conservation or app logs.
- The design is for same-host clocks only. It is invalid if any capture moves to another host/namespace with an unshared clock, if marker pairs are missing, if timestamps move backwards or if packet-level source data are absent. Then the metric is fail-closed unavailable, not approximated.

## Verification needed before any execution approval

1. Review the definition above; no silent implementation.
2. Unit/offline verification: synthetic clocks with constant offset and known drift reproduce exact mapping; missing/backwards markers fail closed; mapped NIC window is not relabeled as app delivery; legacy outputs are unchanged. A single-packet mapping on a future run can be checked against the sender's own first/last payload pairs.
3. Fresh run preflight records `date`, `timedatectl`/NTP state as a descriptive fact, same-host identity, CPU load and marker-pair files. No system clock or service changes.
4. Artifacts retained per run: marker pairs, sender and receiver logs, all captures/drop reports, qdisc counters, backlog series, endpoint records and a hash manifest.
5. Owner's execution approval names the timing-expanded five-run batch explicitly; this clock design alone does not approve traffic.

## Actionable recommendation

Choose the timing-expanded scope for the eventual five-run ce01 support batch, because the intended matched comparison should include NIC timing/rate and the avoidable gap is known before data. The fixed interpretation above is the smallest added definition needed. Do not implement it or ask for execution until the user-facing approval explicitly includes five timing-expanded runs. If the user declines more privileged runs, stop rather than fall back to a minimum batch whose later timing questions are already predictable.
