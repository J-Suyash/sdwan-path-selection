"""Offline-RL hyperparameter sweep (for the laptop or a Colab GPU).

    python scripts/offline_sweep.py --algos discrete_cql \
        --datasets d1 d2 d3 --steps-list 30000 50000 \
        --alphas 0.5 1.0 4.0 --critics 1 2 --device cuda:0

Each configuration is trained, evaluated on the emulator and appended
to --out (analysis/offline_sweep.csv). Models go to offline/models/.
"""

import argparse
import itertools
import os
import time

import pandas as pd
import torch
from d3rlpy.algos import DiscreteBCConfig, DiscreteCQLConfig

from env import SDWanConfig
from offline.learner import build_mdp_dataset, evaluate_actor, greedy_wrapper


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algos", nargs="+", default=["discrete_cql"])
    ap.add_argument("--datasets", nargs="+", default=["d1"])
    ap.add_argument("--steps-list", nargs="+", type=int, default=[50000])
    ap.add_argument("--alphas", nargs="+", type=float, default=[1.0])
    ap.add_argument("--critics", nargs="+", type=int, default=[1])
    ap.add_argument("--eval-episodes", type=int, default=3)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="analysis/offline_sweep.csv")
    args = ap.parse_args()

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        print("CUDA requested but unavailable; falling back to CPU")
        device = "cpu"
    if device.startswith("cuda"):
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    cfg = SDWanConfig()
    rows = []
    cache = {}
    for algo_name, ds_name, steps, alpha, critics in itertools.product(
        args.algos, args.datasets, args.steps_list, args.alphas, args.critics
    ):
        if algo_name == "discrete_bc" and (alpha != args.alphas[0] or critics != 1):
            continue  # BC has no alpha/critics knobs
        if ds_name not in cache:
            print(f"loading {ds_name} ...")
            cache[ds_name] = build_mdp_dataset(ds_name)
        dataset = cache[ds_name]

        tag = f"{algo_name}_{ds_name}_s{steps}_a{alpha}_c{critics}"
        t0 = time.perf_counter()
        if algo_name == "discrete_bc":
            algo = DiscreteBCConfig(batch_size=256).create(device=device)
        else:
            algo = DiscreteCQLConfig(
                batch_size=256, alpha=alpha, n_critics=critics
            ).create(device=device)
        algo.fit(
            dataset,
            n_steps=steps,
            n_steps_per_epoch=max(steps // 5, 1),
            show_progress=False,
        )
        metrics = evaluate_actor(
            greedy_wrapper(algo), cfg, episodes=args.eval_episodes
        )
        metrics.update(
            {
                "algo": algo_name,
                "dataset": ds_name,
                "steps": steps,
                "alpha": alpha,
                "critics": critics,
                "device": device,
                "wall_s": round(time.perf_counter() - t0, 1),
            }
        )
        rows.append(metrics)
        print(metrics)
        os.makedirs("offline/models", exist_ok=True)
        algo.save(f"offline/models/{tag}.d3")

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if os.path.exists(args.out):
        df = pd.concat([pd.read_csv(args.out), df], ignore_index=True)
    df.to_csv(args.out, index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
