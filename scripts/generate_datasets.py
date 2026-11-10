"""Run incumbent controllers in the emulator and log every transition
(proposal Phase 2, Section 8.3 and 10.2).

Datasets:
    D1  single threshold+hysteresis incumbent
    D2  several threshold settings + best-quality + lowest-cost rules
    D3  D2 policies + an epsilon-random policy for coverage

Output: data/datasets/<d>/<policy>_ep<k>.parquet per 1 h episode plus a
manifest CSV. Increase --hours for the full 200 h target; the emulator
runs ~5,000x real time, so 200 simulated hours take a few wall minutes.
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from env import SDWanConfig, SDWanEnv
from policies.incumbents import (
    BestQuality,
    EpsilonRandom,
    Incumbent,
    LowestCostWithinSla,
    ThresholdHysteresis,
)


def policies_for_dataset(name: str) -> list[Incumbent]:
    if name == "d1":
        return [ThresholdHysteresis(5, 30)]
    if name == "d2":
        return [
            ThresholdHysteresis(2, 15),
            ThresholdHysteresis(5, 30),
            ThresholdHysteresis(10, 60),
            BestQuality(),
            LowestCostWithinSla(),
        ]
    if name == "d3":
        return policies_for_dataset("d2") + [EpsilonRandom(0.1)]
    raise ValueError(name)


SIMULATOR_VERSION = "sdwan-fluid-emulator-v2"


def run_episode(
    env: SDWanEnv,
    policy: Incumbent,
    dataset: str,
    episode: int,
    out_dir: str,
    seed: int,
) -> dict:
    obs, _reset_info = env.reset(seed=seed)
    policy.reset(env)
    rows = []
    for _ in range(env.cfg.episode_steps):
        action = policy.act(env)
        behavior_prob = policy.action_probability(env, action)
        if behavior_prob <= 0:
            raise ValueError(
                f"policy {policy.name} reported zero probability for chosen action"
            )
        prev_switch = dict(env.switches)
        next_obs, reward, _, _, info = env.step(action)
        switched = sum(info["switches"][c] - prev_switch[c] for c in env.cfg.classes)
        rows.append(
            {
                "dataset": dataset,
                "policy": policy.name,
                "episode": episode,
                "t": env.t - 1,
                "obs": obs.astype(np.float32),
                "action": action,
                "reward": float(reward),
                "next_obs": next_obs.astype(np.float32),
                "behavior_action_prob": float(behavior_prob),
                "constraint_vector": json.dumps(
                    {
                        "violated": {
                            c: int(info["per_class"].get(c, {}).get("violated", False))
                            for c in env.cfg.classes
                        },
                        "switched": int(switched),
                    },
                    sort_keys=True,
                ),
                "viol_voice": int(env.recent_violations["voice"][-1]),
                "viol_video": int(env.recent_violations["video"][-1]),
                "viol_interactive": int(env.recent_violations["interactive"][-1]),
                "viol_bulk": int(env.recent_violations["bulk"][-1]),
                "switched": switched,
                "workload_profile": env.cfg.primary_profile,
                "workload_regime": env.cfg.workload_regime or "time_of_day",
                "seed": int(seed),
                "episode_start_hour": float(env.episode_start_hour),
                "policy_version": policy.version,
                "simulator_version": SIMULATOR_VERSION,
                "trace_segment": json.dumps(
                    {
                        "underlays": env.cfg.underlay_source,
                        "episode_start_hour": float(env.episode_start_hour),
                    },
                    sort_keys=True,
                ),
                # Split grouping: episodes are independent by workload
                # seed, profile/regime scenario and trace window.
                # Downstream train/validation/test partitions must group
                # on this key so no window or seed leaks across splits.
                "split_group": json.dumps(
                    {
                        "profile": env.cfg.primary_profile,
                        "regime": env.cfg.workload_regime or "time_of_day",
                        "seed": int(seed),
                        "trace_window_start": env.trace_window_start,
                    },
                    sort_keys=True,
                ),
            }
        )
        obs = next_obs
    frame = pd.DataFrame(rows)
    path = os.path.join(out_dir, f"{policy.name}_ep{episode}.parquet")
    frame.to_parquet(path, index=False)
    return {
        "dataset": dataset,
        "policy": policy.name,
        "episode": episode,
        "file": path,
        "rows": len(frame),
        "violations": {c: int(env.violations[c]) for c in env.cfg.classes},
        "switches": {c: int(env.switches[c]) for c in env.cfg.classes},
        "cost_usd": float(env.cum_cost),
        "workload_profile": env.cfg.primary_profile,
        "workload_regime": env.cfg.workload_regime or "time_of_day",
        "seed": int(seed),
        "policy_version": policy.version,
        "simulator_version": SIMULATOR_VERSION,
        "split_group": json.dumps(
            {
                "profile": env.cfg.primary_profile,
                "regime": env.cfg.workload_regime or "time_of_day",
                "seed": int(seed),
                "trace_window_start": env.trace_window_start,
            },
            sort_keys=True,
        ),
    }


REQUIRED_ACCEPTANCE_FIELDS = (
    "accepted",
    "validation_run_id",
    "code_revision",
    "config_fingerprints",
    "trace_set_sha256",
    "reviewed_by",
    "validation_cases",
)


def validation_is_accepted(acceptance_path: str) -> bool:
    """Cross-engine acceptance gate (owner decision 9 / spec section 6).

    Final (non-preliminary) dataset export requires a reviewed acceptance
    artefact bound to the exact code revision, environment configuration
    fingerprints, trace-set hashes and validation run IDs it covers. A
    file that merely says ``accepted: true`` is not sufficient.
    """

    path = Path(acceptance_path)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    for field in REQUIRED_ACCEPTANCE_FIELDS:
        value = payload.get(field)
        if field == "accepted":
            if value is not True:
                return False
        elif not value:  # non-empty run id, revision, reviewer, lists
            return False
    return True


ACCEPTANCE_PATH = "data/cross_engine_validation_acceptance.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="+", default=["d1", "d2", "d3"])
    ap.add_argument("--hours", type=float, default=60.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--profile", choices=["small", "medium", "large"], default="medium")
    ap.add_argument(
        "--regime", choices=["low", "normal", "peak", "stress"], default=None
    )
    ap.add_argument(
        "--finalize",
        action="store_true",
        help="Export final datasets. Refuses unless cross-engine "
        f"validation acceptance exists at {ACCEPTANCE_PATH}.",
    )
    args = ap.parse_args()

    if args.out is None:
        args.out = "data/datasets" if args.finalize else "data/datasets_preliminary"
    if args.finalize and not validation_is_accepted(ACCEPTANCE_PATH):
        raise SystemExit(
            "refusing to export final datasets: cross-engine validation "
            f"acceptance not found or not accepted at {ACCEPTANCE_PATH}; "
            "generate preliminary datasets (default) instead"
        )

    total_episodes = max(1, round(args.hours))
    manifest = []
    for dataset in args.datasets:
        policies = policies_for_dataset(dataset)
        out_dir = os.path.join(args.out, dataset)
        os.makedirs(out_dir, exist_ok=True)
        for i in range(total_episodes):
            policy = policies[i % len(policies)]
            episode_seed = args.seed + i
            env = SDWanEnv(
                SDWanConfig(primary_profile=args.profile, workload_regime=args.regime),
                seed=episode_seed,
            )
            row = run_episode(env, policy, dataset, i, out_dir, episode_seed)
            manifest.append(row)
            print(
                f"[{dataset}] ep {i:03d} {policy.name:24s} "
                f"rows={row['rows']} cost=${row['cost_usd']:.4f} "
                f"viol={row['violations']}"
            )
    manifest_df = pd.DataFrame(manifest)
    manifest_df.to_csv(os.path.join(args.out, "manifest.csv"), index=False)
    print(f"done: {manifest_df['rows'].sum()} total rows in {args.datasets}")


if __name__ == "__main__":
    main()
