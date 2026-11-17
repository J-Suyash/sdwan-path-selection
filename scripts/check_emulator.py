"""Emulator sanity checks (proposal Phase 1, Week 4 + milestone M1).

Checks:
  - reset/step API and observation shape
  - a full 1-hour episode with random actions completes
  - cost, switch and violation accounting work
  - optional speed benchmark: ``--benchmark`` asserts the 1-hour
    episode completes within ``--benchmark-seconds`` (default 4.0 s,
    the M1 target measured on Apple silicon). Without ``--benchmark``
    the elapsed time is reported but not asserted, because absolute
    speed is hardware-specific.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Make the repo root importable so this script can be invoked directly
# (e.g. by absolute path) from any working directory.
REPO_ROOT = str(Path(__file__).resolve().parents[1])
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from env import SDWanConfig, SDWanEnv


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--benchmark",
        action="store_true",
        help="assert the speed target instead of only reporting elapsed time",
    )
    ap.add_argument(
        "--benchmark-seconds",
        type=float,
        default=4.0,
        help="episode wall-clock budget asserted by --benchmark (default: 4.0 s)",
    )
    args = ap.parse_args()

    env = SDWanEnv(SDWanConfig(), seed=0)
    obs, info = env.reset(seed=0)
    print(f"observation shape: {obs.shape}, action space: {env.action_space}")
    assert obs.shape == env.observation_space.shape

    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    total_reward = 0.0
    for _ in range(env.cfg.episode_steps):
        obs, reward, _terminated, truncated, info = env.step(int(rng.integers(81)))
        total_reward += reward
        assert not truncated
    elapsed = time.perf_counter() - t0

    speedup = env.cfg.episode_duration_s / elapsed
    print(f"1 h episode: {elapsed:.2f} s ({speedup:,.0f}x real time)")
    print(f"cumulative cost: ${info['cum_cost_usd']:.6f}")
    print(f"switches: {info['switches']}")
    print(f"violations: {info['violations']}")
    if args.benchmark:
        assert elapsed < args.benchmark_seconds, (
            f"speed target not met: {elapsed:.2f} s >= {args.benchmark_seconds:.2f} s"
        )
    assert info["cum_cost_usd"] > 0
    assert sum(info["switches"].values()) > 0
    print("EMULATOR CHECKS PASSED")


if __name__ == "__main__":
    main()
