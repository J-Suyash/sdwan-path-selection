"""Offline dataset loading, training and evaluation helpers.

Datasets come from scripts/generate_datasets.py (one Parquet per
episode). We build d3rlpy MDPDatasets and expose a generic greedy
evaluation that reuses the emulator.
"""

import glob
import os

import numpy as np
import pandas as pd
from d3rlpy.dataset import MDPDataset

from env import SDWanConfig, SDWanEnv


def load_transitions(dataset: str, data_root: str = "data/datasets") -> dict:
    files = sorted(glob.glob(os.path.join(data_root, dataset, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet files for dataset {dataset}")
    parts = [pd.read_parquet(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    # Files are episode-level, but concatenation order must not be used as the
    # terminal definition. Mark boundaries from behavior-policy identity and
    # episode id so mixed datasets cannot leak continuation transitions.
    group_cols = ["policy", "episode"]
    if "seed" in df.columns:
        group_cols.append("seed")
    if not set(group_cols).issubset(df.columns):
        raise ValueError("offline rows must include policy and episode metadata")
    df = df.sort_values(group_cols + ["t"], kind="stable").reset_index(drop=True)
    obs = np.vstack([np.asarray(x, dtype=np.float32) for x in df["obs"]])
    actions = df["action"].to_numpy(dtype=np.int64)
    rewards = df["reward"].to_numpy(dtype=np.float32)
    terminals = np.zeros(len(df), dtype=np.float32)
    boundaries = df[group_cols].ne(df[group_cols].shift(-1)).any(axis=1)
    terminals[boundaries.to_numpy()] = 1.0
    if "behavior_action_prob" in df:
        probs = df["behavior_action_prob"].to_numpy(dtype=np.float32)
        if not np.isfinite(probs).all() or (probs <= 0).any() or (probs > 1).any():
            raise ValueError("behavior_action_prob must be finite and in (0, 1]")
    else:
        raise ValueError(
            "dataset has no behavior_action_prob; regenerate with "
            "scripts/generate_datasets.py before WIS"
        )
    return {
        "observations": obs,
        "actions": actions,
        "rewards": rewards,
        "terminals": terminals,
        "next_observations": np.vstack(
            [np.asarray(x, dtype=np.float32) for x in df["next_obs"]]
        )
        if "next_obs" in df
        else None,
        "behavior_action_probs": df["behavior_action_prob"].to_numpy(dtype=np.float32),
        "meta": df[
            [
                c
                for c in [
                    "policy",
                    "episode",
                    "seed",
                    "workload_profile",
                    "workload_regime",
                    "simulator_version",
                ]
                if c in df
            ]
        ],
        "frame": df,
    }


def build_mdp_dataset(dataset: str, data_root: str = "data/datasets") -> MDPDataset:
    t = load_transitions(dataset, data_root)
    return MDPDataset(
        observations=t["observations"],
        actions=t["actions"],
        rewards=t["rewards"],
        terminals=t["terminals"],
    )


def evaluate_actor(act_fn, cfg: SDWanConfig, episodes: int = 5, seed: int = 0) -> dict:
    """Run a greedy actor in the emulator and report the paper metrics."""
    env = SDWanEnv(cfg, seed=seed)
    costs, viols, switches = [], [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep)
        for _ in range(cfg.episode_steps):
            action = act_fn(obs)
            obs, _, terminated, _, _ = env.step(int(action))
            if terminated:
                break
        info = env._info()
        costs.append(info["cum_cost_usd"])
        viols.append(info["violations"])
        switches.append(info["switches"])
    return {
        "cost_per_h": float(np.mean(costs)),
        "viol_voice_per_h": float(np.mean([v["voice"] for v in viols])),
        "viol_video_per_h": float(np.mean([v["video"] for v in viols])),
        "viol_interactive_per_h": float(np.mean([v["interactive"] for v in viols])),
        "switches_per_min": float(
            np.mean([sum(s.values()) / (cfg.episode_duration_s / 60) for s in switches])
        ),
    }


def greedy_wrapper(learner):
    """Wrap a d3rlpy learner into a callable for evaluate_actor."""

    def act(obs):
        a = learner.predict(np.asarray(obs, dtype=np.float32).reshape(1, -1))
        return int(np.asarray(a).ravel()[0])

    return act
