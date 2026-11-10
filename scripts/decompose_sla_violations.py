"""SLA violation decomposition (verification spec section 3).

Attribute every class-step SLA violation to its physical causes --
outage, one-way path delay, queueing delay, jitter, trace loss, queue
drop, switching disruption -- per class, underlay, seed and
oneway_delay_factor setting. Cause flags are multi-label (a step can
breach delay and jitter simultaneously); counts are therefore reported
per cause, not as a partition, and overlaps are visible in the output.

    uv run python scripts/decompose_sla_violations.py \
        --out analysis/sla_violation_decomposition.csv

Reference policy: ThresholdHysteresis (the safety-reference incumbent).
"""

import argparse
import time

import numpy as np
import pandas as pd

from env import SDWanConfig, SDWanEnv
from policies.incumbents import ThresholdHysteresis

FACTORS = (0.45, 0.5, 0.55)


def diagnose(env: SDWanEnv) -> list[dict]:
    """Recompute per-class QoS for the step just taken and attribute causes.

    Re-calls _class_qos with the same step index (deterministic given the
    post-step environment state), restoring the violation counters the
    extra call perturbs.
    """

    idx = env.t - 1
    saved_violations = dict(env.violations)
    saved_recent = {c: list(env.recent_violations[c]) for c in env.cfg.classes}
    rows = []
    for cls in env.cfg.classes:
        d = env._class_qos(cls, idx)
        underlay = env.assignment[cls]
        series = env.series[underlay]
        rtt = float(series["rtt_ms"][idx])
        oneway = rtt * env.cfg.oneway_delay_factor
        thr_d, thr_j, thr_l = env.cfg.sla[cls]
        up = bool(series["up"][idx]) and float(series["capacity"][idx]) > 0.0
        delay_breach = d["delay"] > thr_d
        trace_delay_breach = up and oneway > thr_d
        queue_delay_breach = up and not trace_delay_breach and delay_breach
        trace_loss = float(np.clip(series["loss"][idx], 0.0, 1.0))
        disrupted_frac = min(
            env.cfg.decision_interval_s,
            max(0.0, env.disrupt_until[cls] - idx * env.cfg.decision_interval_s),
        ) / env.cfg.decision_interval_s
        rows.append(
            {
                "class": cls,
                "underlay": underlay,
                "step": idx,
                "violated": bool(d["violated"]),
                "cause_outage": not up,
                "cause_delay_trace": trace_delay_breach,
                "cause_delay_queue": queue_delay_breach,
                "cause_jitter": d["jitter"] > thr_j,
                "cause_loss_trace": up and trace_loss > thr_l,
                "cause_loss_queue": up and trace_loss <= thr_l and d["loss"] > thr_l,
                "cause_switch_disruption": disrupted_frac > 0.0 and d["violated"],
                "rtt_ms": round(rtt, 3),
                "oneway_delay_ms": round(oneway, 3),
                "queue_delay_ms": round(d["delay"] - oneway, 3) if up else np.nan,
                "jitter_ms": round(d["jitter"], 3),
                "loss": round(d["loss"], 5),
                "trace_loss": round(trace_loss, 5),
                "disrupted_frac": round(disrupted_frac, 4),
            }
        )
    env.violations.update(saved_violations)
    for cls in env.cfg.classes:
        env.recent_violations[cls].clear()
        env.recent_violations[cls].extend(saved_recent[cls])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--profile", type=str, default="medium")
    parser.add_argument(
        "--factors", type=float, nargs="+", default=list(FACTORS)
    )
    parser.add_argument(
        "--calibrated", action="store_true", default=True
    )
    parser.add_argument("--out", type=str, default="analysis/sla_violation_decomposition.csv")
    args = parser.parse_args()

    rows = []
    for factor in args.factors:
        cfg = SDWanConfig(primary_profile=args.profile)
        cfg.oneway_delay_factor = factor
        if args.calibrated:
            cfg.switching_calibration_path = "data/switching_calibration.csv"
        policy = ThresholdHysteresis()
        for seed in range(args.episodes):
            t0 = time.time()
            env = SDWanEnv(cfg, seed=seed)
            env.reset(seed=seed)
            policy.reset(env)
            steps = 0
            while True:
                action = policy.act(env)
                _, _, terminated, _, _ = env.step(int(action))
                rows.extend(
                    {**d, "seed": seed, "oneway_delay_factor": factor}
                    for d in diagnose(env)
                )
                steps += 1
                if terminated:
                    break
            print(
                f"factor={factor} seed={seed}: {steps} steps, "
                f"violations={dict(env.violations)} "
                f"({time.time() - t0:.1f}s)"
            )

    frame = pd.DataFrame(rows)

    cause_columns = [
        "cause_outage",
        "cause_delay_trace",
        "cause_delay_queue",
        "cause_jitter",
        "cause_loss_trace",
        "cause_loss_queue",
        "cause_switch_disruption",
    ]
    summary = (
        frame.groupby(["oneway_delay_factor", "seed", "class", "underlay"])
        .agg(
            steps=("step", "count"),
            violations=("violated", "sum"),
            **{c: (c, "sum") for c in cause_columns},
        )
        .reset_index()
    )
    frame.to_csv(args.out, index=False)
    summary.to_csv(args.out.replace(".csv", "_summary.csv"), index=False)
    print(f"\nwrote {len(frame)} class-step rows to {args.out}")
    print(f"wrote {len(summary)} summary rows to {args.out.replace('.csv', '_summary.csv')}")
    print(
        summary.groupby("oneway_delay_factor")[
            ["violations"] + cause_columns
        ].sum().to_string()
    )


if __name__ == "__main__":
    main()
