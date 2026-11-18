# Clock mapping and next-batch readiness assessment

18 November 2026. Review only, from recorded code/artifacts and the three executed diagnostics. No implementation or new traffic is recommended by this assessment.

## Is clock mapping a prerequisite to the intended next comparison?

For full-run loss and the planned small ce01 instrumentation/variability batch: no. The full drained run has counter/capture packet conservation, and a whole-capture count is already the network packet basis. The runner's explicit endpoint, actual host sampling lateness and drain status are recorded. A full-run rate using the endpoint denominator can be reported as one descriptive rate, while capture totals establish delivery/loss. This avoids claiming that an epoch capture span equals the monotonic endpoint.

Clock mapping is prerequisite only for a narrower next comparison: exact matched-window NIC-side rate, packet-level capture delay distributions, or per-packet capture timing joins to the application log. Those are not the minimum questions the current five-run proposal answers. Therefore clock mapping is a prerequisite to a later rate/time-distribution comparison, not to every intended next support comparison.

It is still an avoidable instrumentation gap if the next batch later asks for NIC-side matched-window rate. Fixing it after five runs would invite a rerun. An owner-reviewed mapping design should therefore be recorded before batch approval, but implementing it is not automatically justified merely because it is known.

## Would five runs as currently instrumented leave a predictable avoidable gap?

Yes, if their stated decision value includes NIC-window rate or packet-level timing. The captures use epoch time and matched_window uses monotonic time; no mapping is recorded. Whole-capture counts would still be useful, but a windowed NIC rate would remain unavailable. That is not a fatal defect for the proposed minimum batch, which asks whether endpoint artifacts are complete and how the full drained-run network accounting varies. It is a predictable gap for a broader timing claim.

A second avoidable gap is not clock mapping but sample size: five repetitions describe variability and instrumentation completeness; they do not produce a defensible uncertainty estimate or acceptance band. Another is interpretation: ce01 remains sustained-sag-by-working-choice, so repeatability under this input does not prove original case intent.

## Legacy app-metric dependency audit

The code path is now concrete: `testbed/analyze.py summarize_traffic` uses receiver-log arrivals for loss denominator/numerator, throughput duration, delay/jitter and interruption statistics. `testbed/run_switch_calibration.py` uses that output, plus TCP pcap counters for TCP loss/reordering. The240-run raw calibration CSVs carry those app-derived values; retained per-run receiver logs are absent, so the buffered-tail defect cannot be ruled in or out per run. Metrics.json and qdisc/tcpdump process logs remain, but they do not restore packet sequence IDs or app timestamps.

No evaluation conclusion has been falsified by this audit, and the corpus is not invalidated. The correct limitation is provenance: legacy app-derived loss/throughput/delay/jitter rows have incomplete raw-log auditability. Switch-model calibration derived from interruption/loss/reordering and the app's timing values must carry that caveat. Existing committed threshold/band drafts built on those rows are proposals, not adopted acceptance rules; this audit adds one more reason not to freeze cross-engine acceptance from them.

## One coherent recommendation

Do not ask for five runs yet. Prepare a single owner-review decision note that separates two experiment choices:

1. Minimum instrumentation/variability batch: five separately recorded ce01 runs under the frozen rules, deciding only whether the corrected protocol is repeatable enough to support later evidence collection. Clock mapping is not needed for its core outputs. It has modest but real decision value because it prevents scaling an untested protocol.
2. Timing-expanded batch: add an owner-frozen epoch/monotonic mapping design first, then five runs, so NIC-window rate and packet-level timing are available if that comparison is actually intended. This avoids a likely rerun but changes scope and requires explicit design review before data.

The smaller first batch is scientifically defensible only if its result is not presented as validation and is explicitly excluded from acceptance-band derivation. The timing-expanded batch is scientifically more complete but needs one additional frozen definition. The smallest defensible next milestone is therefore the written decision between those two options, not more implementation. Until the owner picks one, do not run traffic, add code or merge the current proposals.
