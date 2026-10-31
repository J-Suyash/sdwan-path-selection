"""Emulator sanity checks (proposal Phase 1, Week 4 + milestone M1).

Checks:
  - reset/step API and observation shape
  - a full 1-hour episode with random actions completes
  - speed target: 1-hour episode in under 4 seconds (M1)
  - cost, switch and violation accounting work
"""

import time

import numpy as np

from env import SDWanConfig, SDWanEnv


def main() -> None:
    env = SDWanEnv(SDWanConfig(), seed=0)
    obs, info = env.reset(seed=0)
    print(f"observation shape: {obs.shape}, action space: {env.action_space}")
    assert obs.shape == env.observation_space.shape

    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    total_reward = 0.0
    for _ in range(env.cfg.episode_seconds):
        obs, reward, terminated, truncated, info = env.step(int(rng.integers(81)))
        total_reward += reward
        assert not truncated
    elapsed = time.perf_counter() - t0

    speedup = env.cfg.episode_seconds / elapsed
    print(f"1 h episode: {elapsed:.2f} s ({speedup:,.0f}x real time)")
    print(f"cumulative cost: ${info['cum_cost_usd']:.6f}")
    print(f"switches: {info['switches']}")
    print(f"violations: {info['violations']}")
    assert elapsed < 4.0, "M1 speed target not met"
    assert info["cum_cost_usd"] > 0
    assert sum(info["switches"].values()) > 0
    print("EMULATOR CHECKS PASSED")


if __name__ == "__main__":
    main()
