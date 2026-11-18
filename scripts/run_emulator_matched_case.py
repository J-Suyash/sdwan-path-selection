#!/usr/bin/env python3
"""MATCHED-RUN HARNESS SKELETON for cross-engine emulator cases.

SCAFFOLDING - owner review pending; produces no accepted validation data.
Every artifact is labelled raw_unvalidated_scaffolding.

Runs the Gymnasium emulator under the fixed per-case conditions of
docs/testbed_match.md and testbed/scenarios/case_drafts/, and writes
per-run numeric rows ONLY for metrics the fluid model expresses natively:

* ``loss_frac`` - run-aggregate dropped/offered bytes from the FluidQueue
  accounting (env/queue.py), measured over the FULL RUN window. This
  matches the runner convention: testbed/analyze.py summarize_traffic
  computes over the whole sender-log span with no warmup exclusion.
* ``throughput_mbps`` - delivered bytes over the full-run window (same
  convention).

``interruption_s`` is the calibrated switching-model effect observed at
the scripted switch (env/switching.py). The validation plan expects a
mismatch against the testbed, so it is NEVER written to the numeric
comparator CSV (the comparator reads only case/metric/value and could
otherwise accept it as gate evidence); it goes to
``emulator_informative.csv`` with quality ``informative_expected_mismatch``.

Metrics the aggregate model cannot express natively are NEVER emitted as
numbers. They are recorded in coverage.json with a source-grounded
reason, and the harness exits 2 (fail closed): the numeric rows are
written to ``emulator_metrics.partial.csv`` - never the complete-name
``emulator_metrics.csv`` - and scripts/cross_engine_compare.py refuses
any input table whose sibling coverage.json reports unsupported required
metrics. A partial result cannot be passed onward as complete:

* ``delay_median_ms`` / ``jitter_mean_ms``: the runner metrics are
  per-packet run statistics; the emulator exposes per-decision-step
  aggregates (0.5 * trace RTT + occupancy/service drain estimate,
  env/sdwan_env.py:243-268). An estimator-level mapping is an owner
  definition decision.

Input-unit reconciliation (verified against testbed/sdwan_topology.py and
testbed/analyze.py): the testbed applies ``one_way_delay_ms`` as a netem
delay on one directional link, so the configured value is one-way; the
emulator's delay is 0.5 * trace RTT, hence constant_series carries
rtt_ms = 2 * one_way_delay_ms. The queue limit is netem/TBF
``max_queue_size`` in packets; the matched buffer is
limit_packets * packet_bytes (env/config.py convention). The runner
measures over the full sender-log span with no warmup exclusion, so
numeric rows use the full-run window; the post-warmup window is kept in
the manifest for diagnostics only.
* ``queue_delay_ms``: no per-packet queue delay exists on either side.
  The emulator's aggregate drain estimate (env/sdwan_env.py:243-249) and
  the flagged Mininet residence-minus-base candidate
  (analysis/candidates/queue_delay_proxy.py; smoke: 28.0% negatives,
  reasons hypothesized not established) are both unvalidated.
* ``reordering_frac``: impossible in the fluid model class - no packet
  order exists; reordering enters only as a calibrated jitter input
  (env/sdwan_env.py:270).

Fixed conditions use the matched-mode config inputs (``constant_series``
/ ``fixed_load_mbps`` in env/config.py). Constant series carry zero trace
jitter; per-path case jitter_ms has no expression in this mode and is
listed in the manifest limitations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from env.config import SDWanConfig
from env.sdwan_env import SDWanEnv
from testbed.scenario import CapacityEvent, SwitchEvent, load_scenario

EXPRESSIBLE_METRICS = ("loss_frac", "throughput_mbps", "interruption_s")

UNSUPPORTED_REASONS = {
    "delay_median_ms": (
        "runner metric is a per-packet run statistic; the fluid emulator "
        "exposes per-decision-step aggregate delay (0.5*trace RTT + "
        "occupancy/service drain estimate, env/sdwan_env.py:243-260). "
        "Estimator-level mapping is an owner definition decision."
    ),
    "jitter_mean_ms": (
        "per-packet run statistic vs per-step aggregate jitter "
        "(|delta RTT|*0.5 + 0.2*drain + calibrated reorder input, "
        "env/sdwan_env.py:261-270); constant-series mode carries zero "
        "trace jitter. Owner definition decision."
    ),
    "queue_delay_ms": (
        "no per-packet queue delay on either engine: emulator has an "
        "aggregate occupancy/service drain estimate "
        "(env/sdwan_env.py:243-249); the Mininet residence-minus-base "
        "candidate (analysis/candidates/queue_delay_proxy.py) is "
        "UNVALIDATED (smoke: 28.0% negatives, reasons hypothesized, not "
        "established). Never emitted as an accepted queue_delay_ms."
    ),
    "reordering_frac": (
        "impossible in the fluid model class: no packets, no packet "
        "order. Reordering enters only as a calibrated jitter input "
        "(env/sdwan_env.py:270). Requires an owner/supervisor "
        "model-scope decision."
    ),
}

LIMITATIONS = [
    "constant-series mode carries zero trace jitter; case jitter_ms has "
    "no emulator-side expression in this mode",
    "emulator delay/jitter are per-step aggregates, not per-packet "
    "statistics; no estimator-level mapping is claimed",
    "interruption_s is the calibrated switching-model effect; the "
    "validation plan expects a mismatch against the testbed (informative, "
    "kept out of the comparator CSV in emulator_informative.csv)",
    "capacity events mutate the input series from the event step, "
    "mirroring the testbed tc rate change at the event point",
    "numeric rows cover natively expressible metrics only, over the "
    "full-run window matching testbed/analyze.py (no warmup exclusion); "
    "coverage.json is the fail-closed record for everything else",
    "delay units: testbed netem delay is one-way on a single link; "
    "constant_series rtt_ms = 2 * one_way_delay_ms so that the emulator "
    "0.5 RTT factor reproduces the configured one-way delay",
    "queue convention: testbed limit is netem/TBF max_queue_size in "
    "packets; matched buffer bytes = limit_packets * packet_bytes",
]


def encode_action(assignment: dict[str, str], cfg: SDWanConfig) -> int:
    """Encode a per-class underlay assignment as a Discrete(K**C) action."""
    action = 0
    k = len(cfg.underlays)
    for i, cls in enumerate(cfg.classes):
        action += cfg.underlays.index(assignment[cls]) * (k**i)
    return action


def matched_config(
    scenario, workload_name: str, calibration_path: str | None
) -> SDWanConfig:
    """Build the matched-mode config for one case scenario."""
    unknown = set(scenario.paths) - {"bb", "five_g", "leo"}
    if unknown:
        raise ValueError(f"scenario paths outside emulator underlays: {sorted(unknown)}")
    wl = scenario.workloads[workload_name]
    for other in scenario.workloads.values():
        if other.packet_bytes != wl.packet_bytes:
            raise ValueError(
                "matched buffer sizing needs one packet_bytes across workloads"
            )
    fixed_load = {cls: 0.0 for cls in ("voice", "video", "interactive", "bulk")}
    fixed_load[wl.flow_type] = wl.rate_mbps
    return SDWanConfig(
        episode_seconds=int(wl.duration_s),
        cap_mbps={p: spec.capacity_mbps for p, spec in scenario.paths.items()},
        queue_buffer_bytes={
            p: float(scenario.queue_limit_for(p) * wl.packet_bytes)
            for p in scenario.paths
        },
        constant_series={
            p: {
                "rtt_ms": spec.rtt_ms,
                "loss": spec.loss_pct / 100.0,
                "capacity_mbps": spec.capacity_mbps,
            }
            for p, spec in scenario.paths.items()
        },
        fixed_load_mbps=fixed_load,
        allow_synthetic_traces=False,
        switching_calibration_path=calibration_path,
    )


def required_metrics_from_cases(
    scenario_name: str, cases_path: str | Path
) -> list[str] | None:
    """Look up the case's required metrics in cross_engine_cases.json."""
    match = re.search(r"ce(\d+)", scenario_name)
    if match is None:
        return None
    case_id = f"ce{match.group(1)}"
    data = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    entries = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ident = str(entry.get("id") or entry.get("case") or entry.get("name") or "")
        if case_id in ident:
            metrics = entry.get("metrics")
            return list(metrics) if metrics else None
    return None


def run_case(
    scenario_path: str | Path,
    calibration_path: str | None = None,
    out_dir: str | Path | None = None,
    seed: int = 0,
    required_metrics: list[str] | None = None,
    cases_path: str | Path | None = None,
) -> int:
    """Run one matched case under fixed conditions. Returns an exit code:

    0 - every required metric expressed natively; 2 - incomplete metric
    coverage (fail closed; coverage.json carries the reasons); 1 - error.
    """
    scenario = load_scenario(scenario_path)
    if len(scenario.workloads) != 1:
        print("error: case drafts are single-workload", file=sys.stderr)
        return 1
    (wl_name, wl), = scenario.workloads.items()
    switch_events = [e for e in scenario.events if isinstance(e, SwitchEvent)]
    capacity_events = [e for e in scenario.events if isinstance(e, CapacityEvent)]
    if switch_events and not calibration_path:
        print(
            "error: scenario has switch events; --calibration is required "
            "(fail closed, no uncalibrated switching)",
            file=sys.stderr,
        )
        return 1

    if required_metrics is None:
        if cases_path is None:
            cases_path = Path("testbed/scenarios/cross_engine_cases.json")
        required_metrics = required_metrics_from_cases(scenario.name, cases_path)
    if not required_metrics:
        print(
            "error: required metric set unresolved for this case; refusing "
            "to invent scope",
            file=sys.stderr,
        )
        return 1

    coverage: dict[str, dict[str, str]] = {}
    for metric in required_metrics:
        if metric in EXPRESSIBLE_METRICS:
            coverage[metric] = {"status": "expressible"}
        elif metric in UNSUPPORTED_REASONS:
            coverage[metric] = {
                "status": "unsupported",
                "reason": UNSUPPORTED_REASONS[metric],
            }
        else:
            print(
                f"error: unknown required metric {metric!r}; extend the "
                "harness or escalate, never invent",
                file=sys.stderr,
            )
            return 1

    try:
        cfg = matched_config(scenario, wl_name, calibration_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    event_step = round(wl.warmup_s / cfg.decision_interval_s)
    if capacity_events or switch_events:
        if switch_events:
            start_path = switch_events[0].old_path
        else:
            start_path = capacity_events[0].path
    else:
        start_path = sorted(scenario.paths)[0]

    rows: list[dict[str, str]] = []
    informative_rows: list[dict[str, str]] = []
    windows: list[dict[str, float]] = []
    for rep in range(scenario.repetitions):
        run_seed = seed + rep
        run_id = f"r{rep:02d}"
        env = SDWanEnv(cfg, seed=run_seed)
        env.reset(seed=run_seed)
        # Pin the initial route directly: reset() starts every class on
        # underlays[0], and routing via the first action would fabricate a
        # spurious t=0 switch transient.
        assignment = {cls: start_path for cls in cfg.classes}
        env.assignment = dict(assignment)

        totals = {"full": [0.0, 0.0, 0.0], "post": [0.0, 0.0, 0.0]}
        interruption_observed: float | None = None
        interruption_calibrated = False
        for t in range(cfg.episode_steps):
            if t == event_step:
                for event in capacity_events:
                    env.series[event.path]["capacity"][t:] = event.capacity_mbps
                for event in switch_events:
                    flow_cls = scenario.workloads[event.workload].flow_type
                    assignment[flow_cls] = event.new_path
            _, _, _, _, info = env.step(encode_action(assignment, cfg))
            if t == event_step and switch_events:
                effect = env.switch_effects[wl.flow_type]
                interruption_observed = effect.interruption_s
                interruption_calibrated = effect.calibrated
            offered = sum(q["offered_bytes"] for q in info["queue"].values())
            delivered = sum(q["delivered_bytes"] for q in info["queue"].values())
            dropped = sum(q["dropped_bytes"] for q in info["queue"].values())
            for key, acc in (("full", True), ("post", t >= event_step)):
                if acc:
                    totals[key][0] += offered
                    totals[key][1] += delivered
                    totals[key][2] += dropped

        post_s = (cfg.episode_steps - event_step) * cfg.decision_interval_s
        full_s = cfg.episode_steps * cfg.decision_interval_s
        windows.append(
            {
                "run_id": run_id,
                "full_offered_bytes": totals["full"][0],
                "full_delivered_bytes": totals["full"][1],
                "full_dropped_bytes": totals["full"][2],
                "post_offered_bytes": totals["post"][0],
                "post_delivered_bytes": totals["post"][1],
                "post_dropped_bytes": totals["post"][2],
            }
        )
        # Numeric comparator rows use the FULL-RUN window: the runner
        # (testbed/analyze.py summarize_traffic) computes over the whole
        # sender-log span with no warmup exclusion.
        o, d, dr = totals["full"]
        if "loss_frac" in required_metrics:
            rows.append(
                {
                    "case": scenario.name,
                    "metric": "loss_frac",
                    "value": repr(dr / o if o > 0 else 0.0),
                    "estimator": "fluid_queue_full_run_window",
                    "quality": "expressible",
                    "run_id": run_id,
                    "seed": str(run_seed),
                }
            )
        if "throughput_mbps" in required_metrics:
            rows.append(
                {
                    "case": scenario.name,
                    "metric": "throughput_mbps",
                    "value": repr(d * 8.0 / 1e6 / full_s if full_s > 0 else 0.0),
                    "estimator": "fluid_queue_full_run_window",
                    "quality": "expressible",
                    "run_id": run_id,
                    "seed": str(run_seed),
                }
            )
        if "interruption_s" in required_metrics:
            if interruption_observed is None:
                print(
                    "error: interruption_s required but the case has no "
                    "switch event",
                    file=sys.stderr,
                )
                return 1
            # Informative only, never comparator evidence: the comparator
            # reads just (case, metric, value) and would treat a numeric
            # row as gate data.
            informative_rows.append(
                {
                    "case": scenario.name,
                    "metric": "interruption_s",
                    "value": repr(interruption_observed),
                    "estimator": "switching_calibration_model",
                    "quality": "informative_expected_mismatch",
                    "calibrated": str(interruption_calibrated),
                    "run_id": run_id,
                    "seed": str(run_seed),
                }
            )

    exit_code = 0 if all(
        coverage[m]["status"] == "expressible" for m in required_metrics
    ) else 2

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # Fail closed: incomplete coverage never gets the complete name.
        metrics_name = (
            "emulator_metrics.csv" if exit_code == 0
            else "emulator_metrics.partial.csv"
        )
        with (out / metrics_name).open("w", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "case",
                    "metric",
                    "value",
                    "estimator",
                    "quality",
                    "run_id",
                    "seed",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        if informative_rows:
            with (out / "emulator_informative.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "case",
                        "metric",
                        "value",
                        "estimator",
                        "quality",
                        "calibrated",
                        "run_id",
                        "seed",
                    ],
                )
                writer.writeheader()
                writer.writerows(informative_rows)
        (out / "coverage.json").write_text(
            json.dumps(
                {
                    "scenario": scenario.name,
                    "required_metrics": coverage,
                    "fail_closed": True,
                    "exit_code": exit_code,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        scenario_bytes = Path(scenario_path).read_bytes()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        (out / "run_manifest.json").write_text(
            json.dumps(
                {
                    "label": "raw_unvalidated_scaffolding",
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "git_head": head,
                    "scenario_path": str(scenario_path),
                    "scenario_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
                    "calibration_path": calibration_path,
                    "seed_base": seed,
                    "repetitions": scenario.repetitions,
                    "event_step": event_step,
                    "post_warmup_window_s": post_s,
                    "full_window_s": full_s,
                    "start_path": start_path,
                    "windows": windows,
                    "numeric_csv": metrics_name,
                    "limitations": LIMITATIONS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    unsupported = [m for m in required_metrics if coverage[m]["status"] != "expressible"]
    print(
        f"{scenario.name}: {len(rows)} numeric rows over "
        f"{scenario.repetitions} reps; unsupported required metrics: "
        f"{unsupported or 'none'}; exit {exit_code}"
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--calibration", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cases", default=None)
    args = parser.parse_args(argv)
    return run_case(
        args.scenario,
        calibration_path=args.calibration,
        out_dir=args.out,
        seed=args.seed,
        cases_path=args.cases,
    )


if __name__ == "__main__":
    sys.exit(main())
