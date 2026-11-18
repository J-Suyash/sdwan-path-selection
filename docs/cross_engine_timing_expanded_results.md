# Five timing-expanded ce01 runs: results and limits

Date: 2026-11-18. Branch: instinct/reproducibility-diagnostics. HEAD at execution: 9f1acd3 (source hashes verified fresh before each of the five launches).

## Scope and authority

Five independently launched matched-drain ce01 runs (out dirs `testbed/outputs/ce01-timing-expanded-r01..r05`), executed under the user's scoped approval (WhatsApp reply 2026-11-18 16:12:21 IST, `wamid.HBgMOTE3OTc2NjM2MDM0FQIAEhggQUNENTMxMDQ0OUFBMjhGQkVBMDZFOTkzMjdCODEyNDgA`, to the five-run ask 16:09:50). Approval covered exactly these five runs; it is now fully consumed. No training, no push, no merge to main.

Purpose foreground: repeatability of packet accounting, artifact completeness, and fixed-receiver confirmation. Clock-mapped timing is exploratory only; nothing here is a validation claim.

## Per-run accounting

| run | sent (prequeue capture) | delivered (branch/server capture) | qdisc dropped | conservation | kernel capture drops |
|-----|------------------------|-----------------------------------|---------------|--------------|----------------------|
| r01 | 75000 | 55916 | 19084 | exact | 0 |
| r02 | 75001 | 55898 | 19103 | exact | 0 |
| r03 | 75001 | 55917 | 19084 | exact | 0 |
| r04 | 75001 | 55903 | 19098 | exact | 0 |
| r05 | 75001 | 55905 | 19096 | exact | 0 |

qdisc accounting at 1442 B/pkt on this setup. Event offset 6.0039-6.0073 s; every run drained at the 16 s inspection. Application-observed payload throughput 39.094-39.110 Mbps (denominator: application-received payload over the received window; not a matched-rate claim). App loss 0.254450-0.254703 vs fluid emulator 0.252369: +0.208 to +0.233 pp, descriptive only.

## Receiver verification (sequence sets, not just counts)

For each run, sequence numbers decoded from server-eth0 capture payloads were compared as sets against the receiver application log (`analysis/timing_expanded_20261118/sequence_set_verification.json`). All five runs: sets exactly equal, zero symmetric difference. This verifies receive-logging completeness under the SIGTERM fix; it does not claim socket delivery semantics beyond the capture point.

## Exploratory clock-mapped counts

`analysis/timing_expanded_20261118/mapped_counts.json`, computed with `testbed/clock_map.py` (declared boundary_safety_s=0.001 as a sensitivity assumption; 0.005 s jump alarm; neither tripped).

- Server and postqueue captures: every frame falls strictly inside the mapped window in all five runs (strict lower = envelope upper = frame count, 0 boundary-uncertain).
- Prequeue capture: 12-61 boundary-uncertain frames per run (frames near the window edges given the t0 envelope width).
- t0 sampled epoch interval width 0.71-0.90 s; t1 width 11.6-15.5 ms. These are sampled-envelope widths, not error bounds.

### Clock coverage limitation (stated plainly)

Each run recorded 7 samples: before_traffic, at_first_send_marker, then only tail samples (t0+15s, after-inspection-15s, t0+16s, after-inspection-16s, after_t1). The 1 s cadence was never reached during the ~14 s send, so there is no during-send step detection; observed-step evidence covers only the start and tail regions. Under the frozen where-runtime-allows rule this is expected runner behavior under load, not instrumentation failure; all required markers and brackets were complete in every run, so no stop condition triggered.

## Hygiene

Per-run preflight/postflight verified: s1 unchanged (never removed; user's standing setup untouched), no residual netns/veth, run bridges removed, port 6653 free, no detached suite. Credential files used for privileged launch were shredded after r05 (they were already absent at shred time; recorded as an observation, no conclusion drawn). Runner/traffic sources unchanged throughout the batch.

## Interpretation limits

- "Sustained sag" remains a working interpretation of ce01, not recovered original intent.
- Five runs establish this-scenario accounting/logging repeatability only: not general dependability, not cross-engine agreement, not policy quality.
- The historical buffered-tail defect is strongly supported by exact offline reproduction; it is not a proof about any specific historical receive.
- cal_v1/v2 archives remain unverifiable at per-run granularity (see `cross_engine_calibration_archive_audit.md`).

## Next bounded step

Close the during-send clock-sampling gap offline (runner sampling thread plus tests) before any future timing comparison. Any new traffic run requires a fresh scoped user approval.
