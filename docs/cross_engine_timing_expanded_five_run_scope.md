# Executable five-run timing-expanded ce01 support scope

18 November 2026. Proposal only; no traffic is authorized. Current source commit is `401e156`; final full-suite result for this code must be present before any approval request is sent.

## Frozen interpretation and evidence produced

Each run uses unchanged ce01 inputs (60Mbps UDP, 1400-byte datagrams, five_g nominal150Mbps, sustained30Mbps floor from t=6s through send end). Sustained sag remains a working interpretation, not recovered original intent. The primary supported purpose is fixed-receiver confirmation, per-run artifact completeness, endpoint/accounting repeatability and simple run-to-run spread. Mapped timing counts are exploratory only. It is not model validation, ce02/ce03 boundary evidence, uncertainty estimation or an acceptance band.

Clock labels are conditional: the strict lower and sampled-envelope upper counts hold only under the sampled-clock envelope assumptions. Sparse samples expose observed steps but cannot prove none occurred between samples. Sender-tap epoch-minus-payload-send values include send-to-tap latency and are not clock validation. `t0` has a direct runner-side first-send-marker observation immediately after marker visibility; it is not a synchronous sender-process read. `t1` has direct before/after-inspection brackets. Any interpolation is only supplemental and labeled as such.

## Frozen safety-envelope definition

`boundary_safety_s = 0.001` seconds. This is only a declared sensitivity assumption, fixed before data to prevent outcome fitting. It is not established by the runner's1-second grid, not physically validated, not a statistical acceptance interval and not a bound on unseen wall-clock behavior. `0.005s` is only a detectable-jump alarm threshold, not clock-health assurance. The report will foreground raw bracket widths, sampled epoch interval ranges and counts conditional on this declared envelope. It will not declare true counts bounded or timing validated. If the envelope is wider than the measured window, strict lower count is0; if the jump alarm fires, mapped timing is unavailable.

## Execution shape and stop rule

Five separately recorded runs, one network lifetime per run, each launched with exactly:

```sh
sudo env PYTHONPATH="$PWD" /usr/bin/python3 -m testbed.run_switch_calibration --scenario testbed/scenarios/case_drafts/ce01.json --out testbed/outputs/ce01-timing-expanded-rXX --repetitions 1 --matched-drain
```

`XX` is01-05 and each output directory must not already exist. No `--repetitions 5` batch is used: separate runs isolate cleanup and capacity-state failures. Every run is a temporary Mininet network with namespaces, branch/hub bridges, veths, controller and qdiscs; s1 is untouched; no global cleanup or system setting change. Existing fixed receiver and endpoint instrumentation are used. The nominal first-send-to-bound horizon is19s total (14s send plus up to5s bounded drain), plus0.5s collection grace and setup/sampling/teardown. Per-run wall time is recorded, not promised.

Before each run: verify branch, source hashes, output absence, zero run-netns/veth/bridge/controller collisions, s1 state, detached suite absence, CPU load and credential-handling files. After each: verify no run objects remain, s1 state unchanged, sudo timestamp revoked, credential files absent. Preserve every artifact.

Stop immediately on instrumentation-incomplete evidence, nonzero runner exit, hash/collision/preflight failure, missing marker, missing capture, nonempty initial queue, capture/counter non-conservation, receiver sequence truncation, clock-step unavailability, or cleanup residue. Do not launch remaining runs after a stop condition. An adverse numeric result is not a stop condition and is never replaced; only instrumentation failure stops the series, and the failed run remains recorded.

## Review excerpts

Key source locations for review: `testbed/run_switch_calibration.py` (`record_clock_sample`, `write_clock_samples`, matched-drain clock sample sequence and stop behavior), `testbed/clock_map.py` (`map_boundary`, `mapped_capture_counts`, step detection and labels), `tests/test_clock_map.py` and `tests/test_matched_window.py`. The runner records `clock_samples.json` only in opt-in matched-drain mode; legacy behavior is unchanged.

## Approval ask after suite

If the final full suite passes, ask one explicit approval for five timing-expanded ce01 support runs under this exact scope. State that they are engineering evidence and provenance repair, not research validation. Do not ask if any test fails or if the user's intent shifts away from this support step.
