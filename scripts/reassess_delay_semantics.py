"""Reassess policy rankings and safety classification after the RTT /
one-way-delay correction (owner decision 5, 2026-11-10).

    uv run python scripts/reassess_delay_semantics.py --episodes 3

Evaluates the incumbent controllers and random actions on the emulator
with the corrected delay semantics and appends classification-grade
metrics to analysis/baseline_results.csv with algo=prefixed marker
``rttfix_<policy>``. Not a training run: it is the before/after ranking
reassessment called for by the owner decision.
"""

import argparse
import time

import numpy as np
import pandas as pd

from env import SDWanConfig, SDWanEnv
from policies.incumbents import (
    BestQuality,
    LowestCostWithinSla,
    ThresholdHysteresis,
)


def run(policy, cfg, seed):
    env = SDWanEnv(cfg, seed=seed)
    obs, _ = env.reset(seed=seed)
    policy.reset(env)
    while True:
        action = policy.act(env)
        obs, _, terminated, _, info = env.step(int(action))
        if terminated:
            return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--profile", type=str, default="medium")
    parser.add_argument("--regime", type=str, default=None)
    parser.add_argument("--out", type=str, default="analysis/baseline_results.csv")
    args = parser.parse_args()

    cfg = SDWanConfig(primary_profile=args.profile)
    cfg.workload_regime = args.regime

    policies = {
        "threshold_hysteresis": ThresholdHysteresis(),
        "best_quality": BestQuality(),
        "lowest_cost_within_sla": LowestCostWithinSla(),
        "random": None,  # random joint action, no controller
    }

    rows = []
    for name, policy in policies.items():
        costs, per_class_viol, switches = [], [], []
        for seed in range(args.episodes):
            t0 = time.time()
            if policy is None:
                env = SDWanEnv(cfg, seed=seed)
                env.reset(seed=seed)
                rng = np.random.default_rng(seed)
                while True:
                    _, _, terminated, _, info = env.step(
                        int(rng.integers(env.action_space.n))
                    )
                    if terminated:
                        break
            else:
                info = run(policy, cfg, seed)
            hours = cfg.episode_duration_s / 3600.0
            costs.append(info["cum_cost_usd"] / hours)
            per_class_viol.append(
                {c: v / hours for c, v in info["violations"].items()}
            )
            switches.append(sum(info["switches"].values()) / hours / 60.0)
            wall = time.time() - t0
            rows.append(
                {
                    "algo": f"rttfix_{name}",
                    "profile": args.profile,
                    "seed": seed,
                    "cost_per_h": info["cum_cost_usd"] / hours,
                    **{f"viol_{c}_per_h": v / hours for c, v in info["violations"].items()},
                    "switches_per_min": switches[-1],
                    "wall_s": round(wall, 1),
                }
            )

    frame = pd.DataFrame(rows)
    summary = frame.groupby("algo")[
        ["cost_per_h", "viol_voice_per_h", "viol_video_per_h",
         "viol_interactive_per_h", "switches_per_min"]
    ].mean()
    print(summary.to_string())
    with open(args.out, "a") as fh:
        frame.to_csv(fh, header=fh.tell() == 0, index=False)
    print(f"\nappended {len(frame)} rows to {args.out}")


if __name__ == "__main__":
    main()
