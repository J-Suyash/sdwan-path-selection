# Single ce01 endpoint support result and receiver logging defect

18 November 2026. Engineering characterization only. One privileged run was approved and executed once; there was no silent repeat or new traffic after it. Source and artifact hashes, preflight/postflight, full outputs and analyses are preserved. No research gate, uncertainty estimate, estimator fitting or Stage7 acceptance is claimed.

## Single-run result

Artifacts: `testbed/outputs/ce01-matched-endpoint-support/`. Analysis: `analysis/characterization/endpoint_support_20261118/`. Scenario SHA256 f4944ae2e2db1c66c831b3042df04059702d33d9bf5138c3852ad41003e741e8. Run used the original ce01 inputs, with sustained sag explicitly a working interpretation rather than recovered original intent.

- Both runner and wrapper returned0. Event offset6.003954309009714s. The15s inspection found508packets on five_g;16s found zero on all paths. Actual matched application window16.009727040014695s, sampling lateness0.009727040014695s. No app arrivals after that endpoint appear in the retained log.
- Sender log and sender capture75001packets. Branch/server captures55900each. All three capture logs report0kernel drops. Qdisc55900delivered+19101dropped=75001exactly; final backlog0. Counted bytes80607800/55900=1442exactly. Parent/child counts are propagated, not added.
- Full drained-run network loss19101/75001=0.2546766043119425. Fluid loss0.25236939435968564. Descriptive difference+0.23072099522568612percentage points in this one case. This is not an accepted agreement threshold or repeatability estimate.
- Retained app log54273rows: nominal app loss0.2763696484046879 and app-window payload rate37.96801772327044Mbps. These remain observed log-based statistics, not network-loss estimates. They must not be replaced retroactively with reconstructed data.

The endpoint artifacts are usable in this single case: explicit first-send/event/drain timestamps, actual denominator, queue residuals and count conservation exist. This does not establish endpoint correctness across cases. Captures use epoch timestamps and the endpoint uses monotonic timestamps; no explicit clock mapping was recorded. An exact matched-window NIC throughput is therefore not claimed from whole-capture counts.

## Persistent app gap traced to a reproducible logging defect

`endpoint_app_gap_sequence_audit.py` matches capture UDP sequence headers against receiver.csv. All54273observed app sequence IDs are in the55900-packet NIC capture. The1627missing IDs are only late-send records,13.374115888000233-13.999633244005963s; none are missing from send seconds0-12.

`endpoint_buffer_reproduction.py`, run with the same systemPython3.14.10, found io.DEFAULT_BUFFER_SIZE131072. Writing the55900capture IDs with the same CSV field widths leaves exactly54273visible rows before an explicit flush and55900after. The entire observed receiver sequence list equals the unflushed prefix.66707bytes are pending. Synthetic timestamps preserve field widths only and are never packet-delay measurements.

`endpoint_signal_reproduction.py` independently exercises the actual existing UDP receiver source in a real process with a fake socket, existing capture IDs and synthetic receive times. It sends no traffic. Default SIGTERM returns-15 and reproduces exactly54273rows with the same observed sequence list. An exception-based graceful SIGTERM handler returns0 and preserves all55900records. The runner sends SIGTERM to stop the receiver; the original receiver had buffered CSV writes and no handler, so it did not unwind its file context.

This is strong direct evidence that forced termination can account for the entire observed logging gap. It is not a time machine: the offline test does not prove historical recv calls, exclude simultaneous socket loss or recover original receive timestamps. The original raw log remains authoritative for what was recorded. Earlier descriptions of a NIC-to-app gap remain true as observations; causal socket-overflow claims would have been unjustified.

## Bounded fix, no rerun

`traffic.main` now installs a receiver-only SIGTERM handler that raises SystemExit0. It unwinds the receiver's CSV file context and flushes records already written. It does not fabricate records, alter packet delivery or change scientific estimators. Sender behavior is unchanged. A real subprocess regression tests both the default control path and fixed entrypoint with55900fake records, no real socket. SIGKILL/hard interruption can still bypass flushing; the fix does not promise crash-proof logs.

The approved run used the pre-fix source hash818915ecefa49dff8adb415b719b09b34df95116018245693561e6a586e61c46. Keep that provenance. The fix is for future runs; no privileged repeat is authorized by the original approval.

## Cleanup and next useful work

Fresh preflight recorded16CPUs, load2.34/3.28/3.21, no detached suite,0netns/0veth, only the existing s1 bridge and controller port6653free. Postflight recorded0netns/0veth, run bridges/controller absent and s1 state byte-for-byte unchanged. Credential files were deleted and sudo timestamp revoked. No global cleanup or settings change.

Next independent work is to audit the existing calibration receiver logs for the same sequence-prefix/logging signature and identify which app-derived metrics may be truncated. This is narrower and more useful than collecting another dataset. Do not invalidate all old data by inference or treat synthetic reconstructions as measured application data. Before any future repeated batch, document the logging fix, retain capture-level and app-level bases separately and choose a recorded epoch/monotonic mapping if exact NIC-window rate is needed. Calibration/held-out separation and the unsupported delay/TCP/reordering limitations remain in force.
