# Calibration aggregate provenance audit from retained metadata

Existing artifacts only, no reconstruction and no global corpus verdict. Searches covered the two known calibration output trees in the recovery worktree, their tracked/untracked file lists and project references. A broader personal-file crawl was intentionally not done.

## Retained files found

Each calibration tree has120 run directories. Each retains `metrics.json`, `qdisc_before.txt`, `qdisc_after.txt` and `tcpdump.log`; root manifests and aggregate CSVs remain. The trees do not retain `sender.csv`, `receiver.csv`, `traffic.pcap`, `prequeue.pcap`, `postqueue.pcap` or `backlog-series.log`. Their file list was checked explicitly. This was mistaken earlier as having no per-run evidence; the correction is that qdisc snapshots and capture process logs do remain.

`tcpdump.log` retains each run's listener name, captured packet count, packets received by filter and kernel-drop report. The run's transport, packet size and loss fraction can be matched to `metrics.json`, but no retained per-packet capture sequence IDs exist to test the exact receiver CSV prefix. Any affected app log is gone in these trees.

## Evidence-backed provenance result

The fixed/reproduced defect means abrupt receiver termination can lose a buffered CSV tail. The confirmed current runs show this exactly. For the240 calibration runs, the needed receiver logs are absent, so no individual run is confirmed affected and none is cleared. We cannot verify whether `loss_frac`, app-derived `delay_median_ms`, `delay_p95_ms`, `jitter_mean_ms` or `throughput_mbps` in the aggregate rows used complete logs. This is an auditable provenance gap in the retained archive, not a finding that all raw band values are wrong.

For UDP runs, capture process logs provide packet totals and kernel-drop reports but do not preserve sequence IDs. They cannot replace receiver timing logs. TCP pcap fields were likewise not retained, so TCP retransmission/out-of-order counts cannot be re-derived. Qdisc snapshots provide only run-end counters, not full timing evidence. The metrics' `sent_frames`, `received_frames`, retransmission and reordering values remain the surviving primary values; the application-log basis is not independently re-checkable.

## Boundary

Do not invalidate the240-run calibration corpus as a whole: its switch-effect measurements remain source-backed aggregate evidence, and no capacity-carryover effect was found because all240 runs are switch-only. Equally, do not call its app-derived packet delay/loss/throughput fully verifiable from retained raw logs. Disclose that the archive retains aggregate metrics and process-level capture counts but not the packet-level source logs needed to audit receiver buffering.

Future repeated matched runs must use the fixed receiver and retain sender/receiver logs plus packet captures or, if space requires pruning, a recorded hashed packet-level summary sufficient to distinguish network loss, capture gaps and application logging loss. No new run is proposed by this audit alone. The existing support run is sufficient to establish the logging defect and its scope.

The practical research-support implication is to treat legacy calibration bands as usable only with this provenance caveat and avoid freezing cross-engine acceptance from them. The next evidence-producing milestone should be a deliberately small repeated matched support batch, only after owner approval: enough to estimate runner variability under the corrected instrumentation and frozen definitions, not another large unreviewed sweep. That approval should separately decide whether retained old runs may be combined with new fixed-instrument runs; I recommend keeping them separate.
