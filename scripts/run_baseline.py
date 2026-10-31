"""Train an online baseline on the emulator and evaluate it.

    python scripts/run_baseline.py --algo dqn --steps 100000 --seeds 3
    python scripts/run_baseline.py --algo lagrangian_ppo --steps 100000 --seeds 3

Results are appended to analysis/baseline_results.csv.
"""

import argparse
import os
import time

import numpy as np
import pandas as pd
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from env import SDWanConfig, SDWanEnv
from online.baselines import LagrangianReward


def make_env(cfg, seed, lagrangian=False, lam_v=200.0, lam_s=100.0, eta=0.2):
    def _make():
        env = SDWanEnv(cfg, seed=seed)
        if lagrangian:
            env = LagrangianReward(env, cfg, lam_v0=lam_v, lam_s0=lam_s, eta=eta)
        return env

    return _make


def evaluate(model, cfg, episodes=5, seed=0, deterministic=True):
    env = SDWanEnv(cfg, seed=seed)
    costs, viols, switches = [], [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep)
        for _ in range(cfg.episode_seconds):
            action, _ = model.predict(obs, deterministic=deterministic)
            obs, _, terminated, _, info = env.step(int(action))
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", choices=["dqn", "lagrangian_ppo"], required=True)
    ap.add_argument("--steps", type=int, default=100000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--eval-episodes", type=int, default=5)
    ap.add_argument("--lam-v0", type=float, default=200.0)
    ap.add_argument("--lam-s0", type=float, default=100.0)
    ap.add_argument("--eta", type=float, default=0.2)
    ap.add_argument("--out", default="analysis/baseline_results.csv")
    args = ap.parse_args()

    cfg = SDWanConfig()
    rows = []
    for seed in range(args.seeds):
        t0 = time.perf_counter()
        if args.algo == "dqn":
            env = DummyVecEnv([make_env(cfg, seed)])
            env = VecNormalize(env, norm_obs=True, norm_reward=False)
            model = DQN(
                "MlpPolicy",
                env,
                learning_starts=2000,
                buffer_size=20000,
                train_freq=4,
                gradient_steps=1,
                target_update_interval=2000,
                exploration_fraction=0.4,
                verbose=0,
                device="cpu",
                seed=seed,
            )
        else:
            env = DummyVecEnv(
                [
                    make_env(
                        cfg,
                        seed,
                        lagrangian=True,
                        lam_v=args.lam_v0,
                        lam_s=args.lam_s0,
                        eta=args.eta,
                    )
                ]
            )
            env = VecNormalize(env, norm_obs=True, norm_reward=False)
            model = PPO(
                "MlpPolicy",
                env,
                n_steps=2048,
                batch_size=256,
                n_epochs=10,
                verbose=0,
                device="cpu",
                seed=seed,
            )
        model.learn(total_timesteps=args.steps)
        metrics = evaluate(model, cfg, episodes=args.eval_episodes, seed=seed * 100)
        metrics.update(
            {"algo": args.algo, "seed": seed, "steps": args.steps,
             "wall_s": round(time.perf_counter() - t0, 1)}
        )
        rows.append(metrics)
        print(metrics)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if os.path.exists(args.out):
        df = pd.concat([pd.read_csv(args.out), df], ignore_index=True)
    df.to_csv(args.out, index=False)
    print(df.groupby("algo")[
        ["cost_per_h", "viol_voice_per_h", "viol_video_per_h",
         "viol_interactive_per_h", "switches_per_min"]
    ].mean().round(3))


if __name__ == "__main__":
    main()
