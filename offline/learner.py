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
    obs = np.vstack([np.asarray(x, dtype=np.float32) for x in df["obs"]])
    actions = df["action"].to_numpy(dtype=np.int64)
    rewards = df["reward"].to_numpy(dtype=np.float32)
    terminals = np.zeros(len(df), dtype=np.float32)
    terminals[df["t"].to_numpy() == df["t"].max()] = 1.0
    return {
        "observations": obs,
        "actions": actions,
        "rewards": rewards,
        "terminals": terminals,
        "meta": df[["policy", "episode"]].drop_duplicates(),
    }


def build_mdp_dataset(dataset: str, data_root: str = "data/datasets") -> MDPDataset:
    t = load_transitions(dataset, data_root)
    return MDPDataset(
        observations=t["observations"],
        actions=t["actions"],
        rewards=t["rewards"],
        terminals=t["terminals"],
    )


def evaluate_actor(
    act_fn, cfg: SDWanConfig, episodes: int = 5, seed: int = 0
) -> dict:
    """Run a greedy actor in the emulator and report the paper metrics."""
    env = SDWanEnv(cfg, seed=seed)
    costs, viols, switches = [], [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep)
        for _ in range(cfg.episode_seconds):
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
            np.mean([sum(s.values()) / (cfg.episode_seconds / 60) for s in switches])
        ),
    }


def greedy_wrapper(learner):
    """Wrap a d3rlpy learner into a callable for evaluate_actor."""

    def act(obs):
        a = learner.predict(np.asarray(obs, dtype=np.float32).reshape(1, -1))
        return int(np.asarray(a).ravel()[0])

    return act
