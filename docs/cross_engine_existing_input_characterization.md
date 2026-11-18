# Existing-input characterization and minimum matched support protocol

Status: engineering/debug evidence only, 18 November 2026. No privileged matched run has executed. This report does not replace the original validation plan or approve research results.

## What ran

`analysis/candidates/characterize_existing_inputs.py --run`, with the unchanged four case drafts, existing `data/switching_calibration_v2.csv`, seeds 0-4, five repetitions per case and opt-in drain. Outputs are under `analysis/characterization/existing_inputs_20261118/`. Source hashes, original case definitions, configured inputs and actual windows are in the JSON manifests. No training, estimator tuning, band derivation or acceptance occurred. All four cases exited 2 with partial comparator files. Every emitted metric had identical full-precision numeric strings across repetitions. This is determinism, not empirical repeatability.

The 1400/1442 capacity scale is a working convention for this specific 1400-byte UDP setup, supported by P1's exact counters and exploratory rate/backlog agreement. It is not a general packet-overhead formula, and TCP packet segmentation is not thereby matched. Other payload sizes are rejected rather than extrapolated.

## Coverage map

| Case intent | Actual inputs and harness behavior | Missing observable or mismatch |
| --- | --- | --- |
| ce01 queue saturation | 60 Mbps UDP, five_g 150 to 30 Mbps nominal at 6s, 14s send, 37.5ms base one-way delay. Sustained sag through end is a working interpretation, not recovered original intent. Scaled service; 16s actual window, 2s drain, zero residual. Loss 0.25236939435968564; payload rate 39.25060679611651 Mbps. | queue_delay_ms unsupported; packet delay-line occupancy is not fluid queue occupancy. Throughput includes drain time, not legacy arrival span. |
| ce02 voice delay boundary | 0.12 Mbps UDP, leo 31ms to five_g 37.5ms, zero loss. Fluid loss 0; full-episode time-weighted delay candidate 37.5ms, jitter candidate 0. | Not near voice's configured 150ms one-way threshold. Netem jitter 0.3/1ms is absent from constant-series emulator. Delay/jitter candidates remain unsupported in coverage. |
| ce03 interactive TCP loss boundary | 2 Mbps TCP label, five_g 37.5ms to leo 31ms, zero configured loss. Fluid loss 0; delay candidate 31ms. | No TCP retransmission, congestion-control or reordering observable in fluid model. Not a 5% retransmission-loss boundary. Packet segmentation/accounting differs. |
| ce04 video switch transient | 4 Mbps UDP, leo 31ms to bb 93.7ms. Fluid loss 0; interruption model output 0.06269378501019673s, informative only. | Calibration-derived interruption is not independent validation. Reordering unsupported; application switch-loss equivalence not established. |

ce02-ce04 use 15s windows including one post-send inspection step, with zero residual. Candidate delay/jitter statistics include that step and are informational only. The generator records their weighting rather than changing it against observations.

## Endpoint plumbing

Legacy calibration behavior remains unchanged. Opt-in `--matched-drain` adds:

- An atomic first-send monotonic timestamp marker. Event timing and inspection boundaries are anchored to it instead of process-launch time.
- A shared bound: ceiling of send duration plus 3 times maximum payload buffer divided by minimum scaled payload service. Current drafts yield maximum 19s for ce01 and 16s for ce02-ce04. First inspection is at send-end plus 1s.
- All-path qdisc checks, retaining the largest parent/child backlog per path rather than adding propagated counters. Missing backlog data fails closed. Qdisc wire-byte and packet units stay separate from fluid payload bytes.
- Receiver lifetime through the bound, actual inspection timestamps and lateness, drain/bound-hit status, and separately named application matched-window counts/rate. Legacy metrics retain their original denominator.
- A pre-repetition empty-queue check and restoration of initial capacities, because one Mininet network is reused and ce01's preceding repetition otherwise leaves its 30Mbps floor installed.

`matched_window.json` reports actual t0/t1 and any arrivals after the window. A 0.5s collection grace is not added to the matched denominator. No equality is asserted between host inspection time and the emulator's ideal decision grid. A queue-empty sample does not prove absence of packets already dequeued toward the application. Capture-level counts, capture-drop counters and application counts must therefore be reconciled separately. The observed NIC-to-application gap remains mechanistically unexplained.

## Smallest next evidence-producing batch

Recommendation after tests and explicit scoped permission: one ce01 UDP support run, not four boundary-validation cases and not a Stage-7 pass. It tests whether the new anchored endpoint artifacts, backlog accounting and capture/application reconciliation are usable before spending five repetitions per case. Keep all original inputs, declare sustained sag, opt into matched drain and cap the send-plus-drain observation at 19s plus measured sampling overhead. Preserve sender, receiver, three captures, capture-drop logs, all-path qdisc inspection snapshots and matched-window artifacts. No acceptance band is derived. No silent rerun if instrumentation fails or evidence conflicts.

A later repeated batch can characterize variability only after this plumbing check. Within-engine calibration rules and estimator treatment must be justified and frozen before held-out cross-engine evaluation. The existing deterministic fluid repetitions do not supply estimator uncertainty.

## Boundary candidates for student review, not executed inputs

Source: `env/config.py` defines voice one-way delay 150ms and interactive loss fraction 0.05. A voice boundary experiment would need an explicitly chosen below/at/above-150ms operating-point family and a fixed packet-vs-time estimator/window; the current 31/37.5ms inputs cannot stand in for it. No offset from the threshold is invented here.

For interactive traffic, configuring 5% netem packet loss would not establish 5% application loss or a 5% TCP retransmission statistic. The student must choose the target observable before selecting inputs; a paired UDP packet-loss diagnostic could test packet accounting, but is not a substitute for the original TCP claim. No replacement case, new contribution or tuned acceptance criterion is created.
