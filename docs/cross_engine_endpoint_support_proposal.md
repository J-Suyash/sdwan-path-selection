# Scoped proposal: one ce01 endpoint-support run

Prepared 18 Nov 2026. Proposal only. No privileged execution approved or performed for this proposal. This is not the four-case validation batch or an acceptance test.

## Decisive purpose

Close the engineering uncertainty about whether the opt-in anchored sender/event/drain instrumentation creates usable, internally auditable observations. The existing ce01 saturation inputs exercise a real queue and drain tail. Do not redesign ce02/ce03 to obtain a convenient result.

The run is useful only if it records a first-send marker, event offset, all-path pre/post-reset qdisc state, post-send inspection times, an explicit drain/bound-hit reason, actual denominator, three capture counts/drop reports and application matched-window counts. Missing evidence means instrumentation-incomplete, not a scientific failure or pass. Reconcile capture-to-application gaps without inventing their cause. Report residuals and host sampling lateness directly; do not add an ad-hoc tolerance. Unsupported delay/reordering and calibrated interruption remain outside acceptance.

## Fixed inputs

- Current branch: instinct/reproducibility-diagnostics, worktree /home/sxtr/Projects/Major Project-instinct-recovery.
- Scenario: testbed/scenarios/case_drafts/ce01.json, SHA256 f4944ae2e2db1c66c831b3042df04059702d33d9bf5138c3852ad41003e741e8.
- Runner: testbed/run_switch_calibration.py, SHA256 6da834ff1666d2809a67fdb3fa03ea9ea52e4cea6a624ce4ce15f43c6856452b.
- Shared endpoint helper: testbed/matched_window.py, SHA256 9552a2c35b7b133048ce2e563278331f4f9d3f64c1c6ebb85579bae194b5e1ad.
- Traffic helper: testbed/traffic.py, SHA256 818915ecefa49dff8adb415b719b09b34df95116018245693561e6a586e61c46.
- One repetition only. Internal 60Mbps UDP, 1400-byte datagrams, 14s send. five_g nominal150Mbps initially, sustained30Mbps floor from t=6s through end. Sustained sag is a working interpretation, not recovered original intent. Base one-way delay37.5ms, jitter1ms, configured loss0, packet limit3125. Other path capacities and queue sizes remain the original draft's.
- Working fluid capacity scale1400/1442 is setup-specific with exploratory P1 provenance. No model tuning.
- Common post-send inspection grid1s; shared maximum nominal horizon19s from first send. Actual host sampling overhead is recorded, not hidden inside claimed exact timing. Up to0.5s collection grace after the endpoint is excluded from its denominator.

## Exact command after approval and fresh preflight

From the worktree:

```sh
sudo env PYTHONPATH="$PWD" /usr/bin/python3 -m testbed.run_switch_calibration --scenario testbed/scenarios/case_drafts/ce01.json --out testbed/outputs/ce01-matched-endpoint-support --repetitions 1 --matched-drain
```

The privileged wrapper must use approved secret handling without printing credentials. The target output directory must not exist. Recheck hashes, current branch and scoped permissions immediately before launch. The previously generated unprivileged plan is testbed/outputs/ce01-matched-endpoint-dryrun/dry_run_plan.json; generate the final target's dry-run plan before execution.

## Side effects, collision and cleanup checks

Temporary Mininet namespaces/hosts, s_branch and s_hub bridges, path/client/server veths, controller listening on6653 and tc qdiscs, plus local captures/logs. Check those exact resources for collision before launch. Existing s1 must remain untouched, currently observed DOWN. No global mn -c, training, system-setting change, push, merge or branch creation. Setup/teardown add time beyond the14s send and nominal5s drain allowance.

Use only the run's normal network stop or targeted cleanup of its recorded objects. Verify no residual run namespaces/veths/bridges/controller and compare s1's before/after state. Revoke sudo timestamp and remove credential-transfer files. A hard interruption may leave temporary objects needing targeted cleanup. A failed/inconclusive support run does not authorize a silent repeat.

## Provenance impact of the rate-restoration fix

Audit of current recorded output directories found cal_v1_full and cal_v2_perpath each contain120 switch-only metrics (ovs-ofctl flow modification), not capacity events. ce01-smoke and P1 each contain exactly one planned and measured capacity-event run. Thus no recorded prior multi-repetition capacity-event dataset was identified as affected. The240-run switch-only corpus is not invalidated by this defect. The fluid characterization starts a fresh environment each repetition and was unaffected. Opt-in restoration is before measurement, leaves legacy callers unchanged, rejects nonempty initial queues and records expected rates plus actual qdisc text.
