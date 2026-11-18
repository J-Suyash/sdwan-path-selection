# Small repeated ce01 support protocol (proposal only)

18 November 2026. Prepared for owner review; not approved, not executed and not a Stage7 validation batch. Inputs are the unchanged current ce01 draft:60Mbps UDP, 1400-byte datagrams, nominal five_g150Mbps, sustained floor30Mbps from t=6s through send end. Sustained sag remains a working interpretation, not recovered original intent. No new traffic is authorized by this proposal.

## Decision it would settle

The single support run established that the corrected endpoint instrumentation can produce one auditable endpoint record, but n=1 cannot characterize run-to-run variability. A small repeated batch would settle these engineering questions under frozen interpretation:

1. Do the pre-run queue check, first-send marker, actual event offset, post-send drain checks and capture/app/counter reconciliation produce complete records on every repetition?
2. Under the same unchanged inputs, how much do runner-side counter loss, full-capture delivery, actual endpoint times and matched app-window rate vary across repetitions?
3. How large is sampling/host timing variability, using actual measured offsets and lateness rather than assuming the1s grid?
4. Is the fixed receiver free of abrupt-termination tail loss, verified per run by retained sender/receiver/capture sequence-level artifacts?
5. Which remaining differences are protocol artifacts versus model simplifications, before any owner chooses a research acceptance rule?

## What it would not settle

It would not validate the emulator as a scientific model, validate ce02/ce03 boundary coverage, or prove that the original case names describe their current operating points. It would not estimate cross-engine uncertainty from five repetitions or set acceptance bands. It would not justify TCP behavior from UDP results. It would not resolve packet-vs-time delay weighting, reordering, delay-line versus queue occupancy, or the calibrated interruption circularity. It would not replace an owner decision on the original ce01 transient-versus-sustained intent.

The one-ce01 result would support or reject only the corrected ce01 measurement path. Its outcome cannot be generalized to ce02/ce03/ce04 without separate evidence.

## Fixed interpretation before data

Freeze these rules before any data are collected:

- Repetitions:5, same order, same seeds for fluid harness characterization (seeds0-4; determinism is not empirical spread). One privileged runner repetition per emulator case repetition, or a documented reason not to pair them. No repetition is dropped because its numerical result is unfavorable.
- Legacy metrics remain unchanged and separate. Matched-window application counts/rates are new diagnostics, not retroactive replacements.
- Full-run counter loss is reported over the drained run as delivered/(delivered+dropped). A full-capture delivered count is not substituted for matched-window app receipt.
- The emulator actual window is steps-run x1s under opt-in drain. The runner actual window is the final sampled endpoint; sampling lateness is reported. No denominator equality is assumed.
- No significance claim, confidence interval or acceptance threshold is assigned after seeing results. Any dispersion reported is a range/spread summary with n=5 plainly labeled.
- Epoch capture timestamps and monotonic runner timestamps remain unlinked. Exact matched-window NIC rate remains unavailable until the owner chooses and implements a recorded clock mapping.
- A run with missing marker, missing capture, nonempty initial queue, counter/capture non-conservation, receiver sequence truncation or infrastructure abort is instrumentation-incomplete and is preserved, never silently repeated. If systematic, the protocol stops rather than generating partial results.
- ce01's sustained sag remains labeled a working interpretation. Boundary-case redesign candidates remain separate student-review material.

## Minimum artifacts and execution shape

Each run retains scenario hash, current source hashes, pre/post privileged checks, initial/restored qdisc state, first-send marker, event applied time, drain inspection snapshots, sender/receiver logs, all capture files and process drop reports, qdisc counters, backlog series, `matched_window.json`, legacy `metrics.json` and an explicit record that graceful receiver shutdown returned0. Disk cost is expected to be modest but is measured after the dry run; old data are never deleted to make room without owner approval.

Runner command remains one repetition at a time with `--matched-drain`; batch repetition is requested through five independent planned run records or `--repetitions 5` only if owner explicitly accepts the same-reset behavior now tested. The safer smallest protocol is five separately recorded single runs, so an abort cannot contaminate subsequent runs within one network lifetime. Emulator side is already deterministic; it is run only if a code/input hash changes.

Approximate observation time is14s send plus at most the shared drain bound (nominal first-to-last horizon19s), plus actual setup, sampling and teardown. No acceptance promise is attached to that estimate. Every run is a temporary Mininet network and requires the same scoped cleanup/permission pattern as the approved support run.

## Smallest defensible next milestone

The next owner-facing decision is whether this exact frozen interpretation and five separately recorded single ce01 runs are worth five new privileged runs. If yes, execute them as one explicitly approved bounded batch with pre-run hash/collision/load checks and post-run cleanup checks. If no, stop: write up the instrumentation result and archive provenance caveats as the research support output, and do not keep adding harness machinery.

Independent work that remains useful without new traffic: map capture epoch timestamps to runner monotonic timestamps in future runs using an explicit first-packet marker design for owner review, and finish a bounded review of where aggregate legacy app metrics entered evaluation conclusions. Do not implement clock mapping silently because any mapping changes interpretation and must be frozen first.
