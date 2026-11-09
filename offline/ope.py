"""Small, explicit off-policy evaluation helpers for logged episodes.

These estimators report uncertainty and support diagnostics. They are not
safety guarantees and should be validated in the emulator where true returns
are available.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WISResult:
    estimate: float
    effective_sample_size: float
    normalized_weights: np.ndarray
    episode_returns: np.ndarray
    bootstrap_interval: tuple[float, float] | None


@dataclass(frozen=True)
class FQEResult:
    estimate: float
    initial_values: np.ndarray
    iterations: int
    ridge: float


def _episode_groups(frame: pd.DataFrame):
    required = {"policy", "episode", "reward", "action", "behavior_action_prob"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"WIS input missing columns: {sorted(missing)}")
    group_cols = ["policy", "episode"]
    if "seed" in frame.columns:
        group_cols.append("seed")
    return frame.sort_values([*group_cols, "t"], kind="stable").groupby(
        group_cols, sort=False
    )


def wis(
    frame: pd.DataFrame,
    target_action_probability: Callable[[pd.Series], float],
    gamma: float = 1.0,
    bootstrap: int = 0,
    seed: int = 0,
) -> WISResult:
    """Per-decision trajectory WIS with ESS and optional episode bootstrap."""
    if not 0 < gamma <= 1:
        raise ValueError("gamma must be in (0, 1]")
    rng = np.random.default_rng(seed)
    returns: list[float] = []
    log_weights: list[float] = []
    for _, episode in _episode_groups(frame):
        log_weight = 0.0
        ret = 0.0
        for t, (_, row) in enumerate(episode.iterrows()):
            target = float(target_action_probability(row))
            behavior = float(row["behavior_action_prob"])
            if not np.isfinite(target) or target < 0 or target > 1:
                raise ValueError("target action probabilities must be in [0, 1]")
            if behavior <= 0:
                raise ValueError("behavior action probabilities must be positive")
            if target == 0:
                log_weight = -np.inf
                break
            log_weight += np.log(target) - np.log(behavior)
            ret += gamma**t * float(row["reward"])
        returns.append(ret)
        log_weights.append(log_weight)
    raw = np.asarray(log_weights, dtype=float)
    finite = np.isfinite(raw)
    if not finite.any():
        weights = np.zeros_like(raw)
    else:
        shifted = raw - np.max(raw[finite])
        weights = np.where(finite, np.exp(shifted), 0.0)
    total = float(weights.sum())
    normalized = weights / total if total > 0 else np.zeros_like(weights)
    values = np.asarray(returns, dtype=float)
    estimate = float(np.sum(normalized * values)) if total > 0 else float("nan")
    ess = float(1.0 / np.sum(normalized**2)) if total > 0 else 0.0
    interval = None
    if bootstrap and len(values):
        draws = []
        for _ in range(int(bootstrap)):
            idx = rng.integers(0, len(values), len(values))
            w = normalized[idx]
            draws.append(
                float(np.sum(w * values[idx]) / w.sum()) if w.sum() else np.nan
            )
        interval = tuple(np.nanpercentile(draws, [2.5, 97.5]).tolist())
    return WISResult(estimate, ess, normalized, values, interval)


def support_report(frame: pd.DataFrame, n_actions: int) -> dict:
    """Report action coverage without pretending coverage implies safety."""
    counts = frame["action"].value_counts().reindex(range(n_actions), fill_value=0)
    return {
        "n_actions": int(n_actions),
        "observed_actions": int((counts > 0).sum()),
        "unobserved_actions": [int(a) for a, count in counts.items() if count == 0],
        "min_count_observed": int(counts[counts > 0].min())
        if (counts > 0).any()
        else 0,
        "action_counts": {str(int(a)): int(c) for a, c in counts.items()},
    }


def fqe(
    frame: pd.DataFrame,
    target_action: Callable[[np.ndarray], int],
    n_actions: int,
    gamma: float = 1.0,
    iterations: int = 20,
    ridge: float = 1e-5,
) -> FQEResult:
    """Linear fitted-Q evaluation for a discrete target policy.

    The estimator is intentionally transparent and model-free. It is a
    baseline for validating OPE in the emulator, not a deployment guarantee.
    ``target_action`` receives one observation and returns an action index.
    """
    required = {"obs", "next_obs", "action", "reward", "policy", "episode", "t"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"FQE input missing columns: {sorted(missing)}")
    if n_actions <= 0 or iterations <= 0 or not 0 <= gamma <= 1:
        raise ValueError("invalid FQE hyperparameters")
    frame = frame.reset_index(drop=True)
    observations = np.vstack([np.asarray(x, dtype=np.float64) for x in frame["obs"]])
    next_observations = np.vstack(
        [np.asarray(x, dtype=np.float64) for x in frame["next_obs"]]
    )
    actions = frame["action"].to_numpy(np.int64)
    rewards = frame["reward"].to_numpy(np.float64)
    group_cols = ["policy", "episode"]
    if "seed" in frame.columns:
        group_cols.append("seed")
    groups = frame.sort_values([*group_cols, "t"], kind="stable").groupby(
        group_cols, sort=False
    )
    terminals = np.zeros(len(frame), dtype=np.float64)
    terminals[frame.groupby(group_cols, sort=False).tail(1).index] = 1.0

    def features(states: np.ndarray, action_values: np.ndarray) -> np.ndarray:
        one_hot = np.eye(n_actions, dtype=np.float64)[action_values]
        return np.concatenate([states, one_hot], axis=1)

    design = features(observations, actions)
    weights = np.zeros(design.shape[1], dtype=np.float64)
    gram = design.T @ design + ridge * np.eye(design.shape[1])
    for _ in range(iterations):
        next_actions = np.asarray(
            [int(target_action(obs)) for obs in next_observations], dtype=np.int64
        )
        if ((next_actions < 0) | (next_actions >= n_actions)).any():
            raise ValueError("target_action returned an action outside n_actions")
        targets = rewards + gamma * (1.0 - terminals) * (
            features(next_observations, next_actions) @ weights
        )
        weights = np.linalg.solve(gram, design.T @ targets)

    initial_rows = groups.head(1)
    initial_values = []
    for _, row in initial_rows.iterrows():
        obs = np.asarray(row["obs"], dtype=np.float64).reshape(1, -1)
        action = np.asarray([int(target_action(obs[0]))], dtype=np.int64)
        if action[0] < 0 or action[0] >= n_actions:
            raise ValueError("target_action returned an action outside n_actions")
        initial_values.append(float((features(obs, action) @ weights)[0]))
    values = np.asarray(initial_values, dtype=np.float64)
    return FQEResult(
        estimate=float(values.mean()) if len(values) else float("nan"),
        initial_values=values,
        iterations=iterations,
        ridge=ridge,
    )
