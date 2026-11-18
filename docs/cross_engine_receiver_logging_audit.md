# Existing artifact receiver-log audit

18 November 2026. Existing artifacts only. No packet reconstruction, synthetic replacement, traffic or research acceptance. The audit distinguishes evidence-backed truncation signatures from suspects; it does not invalidate any entire corpus by inference.

## Coverage and availability

`testbed/outputs/cal_v1_full` and `cal_v2_perpath` contain committed aggregate `switch_metrics_raw.csv` rows and manifests, but no retained per-run `receiver.csv` or `traffic.pcap` files under their output trees. Therefore their app-derived metrics cannot be directly re-audited here. They are unverified as to this defect, not confirmed affected and not cleared by inference. This availability finding should change evaluation provenance: the 240 raw band CSVs' app-level loss/throughput and packet delay basis cannot now be traced to retained sequence logs in these directories.

Four retained per-run artifacts were auditable. Rule: confirmed only when the receiver sequence list is an exact prefix of the capture's unique sequence list, no app ID is outside capture, sender has more rows and the capture has fewer unique IDs than the sender. Exact capture prefix alone without missing IDs is not a truncation signature.

## Findings

- `ce01-matched-endpoint-support/e00-r00`: confirmed. App54273; sender75001; capture55900; missing capture IDs1627 (71648-74999); exact prefix; no app IDs outside capture. This is the single approved support run.
- `rate-diag-p1/e00-r00`: confirmed. App87273; sender89287; capture89287; missing IDs2014 (87273-89286); exact prefix. This matches the previously observed P1 NIC-to-app difference. The bounded Qdisc counter/rate conclusions used capture and counter bases and remain separate, but the P1 app's 87273-row log must be understood as affected by the abrupt-stop buffering defect.
- `ce01-smoke/e00-r00`: strongly suspect, not confirmed by the exact-prefix rule. App54273; sender75001; capture55608; missing capture IDs1335 (72250-74998); no app IDs outside capture, but receiver is not exactly the capture's first54273rows. Late-tail concentration and exact count54273 are consistent with buffered tail loss. Do not infer whether any earlier socket events also occurred from this run alone.
- `smoke-20261118-033510/e00-r00`: no truncation signature. App782, capture782, no missing capture IDs. Its single sender row outside capture/app is a separate recording or capture boundary matter, not a receiver-tail truncation finding.

The same54273row count in ce01-smoke and ce01-matched-endpoint-support matches Python3.14's131072-byte CSV buffer under the observed field widths, independently reproduced offline. Actual receiver-source SIGTERM testing reproduced the support run's full sequence prefix and preserved all records with a graceful handler. This directly supports forced termination of a buffered writer as a mechanism for confirmed signatures. It does not recover historical receive timestamps and does not prove every historical packet was delivered by the OS.

## Impact on reported metrics

For confirmed runs, app-derived loss and first/last-arrival throughput are logging-incomplete, not valid packet-loss evidence. Capture/counter-derived counts remain the appropriate network basis. App-derived delay/jitter rows are a logged-arrival sample whose tail is missing, not complete packet-level evidence. Missing receiver rows are never reconstructed as measured data.

For the 240-run calibration corpora, no run-level result is changed by inference. The only evidence-backed statement is that their retained raw logs/pcaps are absent from these output trees, so an equivalent sequence audit cannot be performed. The earlier switch-only versus capacity-carryover audit remains about event type and rate reset, not logging truncation. Any future repeated matched batch should use the fixed receiver and retain captures/logs; it should not substitute this audit for data collection.

## Source fix and regression evidence

`testbed/traffic.py` now installs a receiver-only SIGTERM handler that raises SystemExit0 and unwinds buffered CSV context. Sender behavior unchanged. `tests/test_receiver_shutdown.py` launches real subprocesses with a fake socket and 55900 synthetic records under the actual system Python: control path exits by SIGTERM and loses a nonempty buffered tail; fixed path exits0 and preserves all55900records. Tests passed under project Python3.11 and system Python3.14. SIGKILL/hard interruption can still lose unwritten logs.

Raw original logs remain untouched. `analysis/characterization/existing_inputs_20261118/receiver_logging_audit.json` and `analysis/characterization/endpoint_support_20261118/` contain exact run-level evidence and hashes. Audit script: `analysis/candidates/receiver_logging_audit.py`.
