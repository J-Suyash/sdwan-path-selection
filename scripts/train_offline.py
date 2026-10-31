"""Train an offline policy and evaluate it (Phase 3).

    python scripts/train_offline.py --algo discrete_bc --dataset d1 --steps 20000
    python scripts/train_offline.py --algo discrete_cql --dataset d1 --steps 50000

Results append to analysis/offline_results.csv; models are saved under
offline/models/.
"""

import argparse
import os
import time

import pandas as pd
from d3rlpy.algos import DiscreteBCConfig, DiscreteCQLConfig

from env import SDWanConfig
from offline.learner import build_mdp_dataset, evaluate_actor, greedy_wrapper


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", choices=["discrete_bc", "discrete_cql"], required=True)
    ap.add_argument("--dataset", choices=["d1", "d2", "d3"], required=True)
    ap.add_argument("--steps", type=int, default=50000)
    ap.add_argument("--eval-episodes", type=int, default=5)
    ap.add_argument("--eval-seed", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="analysis/offline_results.csv")
    args = ap.parse_args()

    cfg = SDWanConfig()
    dataset = build_mdp_dataset(args.dataset)
    print(f"dataset {args.dataset}: {dataset.transition_count} transitions")

    t0 = time.perf_counter()
    if args.algo == "discrete_bc":
        algo = DiscreteBCConfig(batch_size=256).create(device=args.device)
    else:
        algo = DiscreteCQLConfig(batch_size=256).create(device=args.device)
    algo.fit(
        dataset,
        n_steps=args.steps,
        n_steps_per_epoch=max(args.steps // 5, 1),
        show_progress=False,
    )
    wall_s = time.perf_counter() - t0

    metrics = evaluate_actor(
        greedy_wrapper(algo), cfg, episodes=args.eval_episodes, seed=args.eval_seed
    )
    metrics.update(
        {
            "algo": args.algo,
            "dataset": args.dataset,
            "steps": args.steps,
            "wall_s": round(wall_s, 1),
        }
    )
    print(metrics)

    model_dir = os.path.join("offline", "models")
    os.makedirs(model_dir, exist_ok=True)
    algo.save(os.path.join(model_dir, f"{args.algo}_{args.dataset}.d3"))

    df = pd.DataFrame([metrics])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if os.path.exists(args.out):
        df = pd.concat([pd.read_csv(args.out), df], ignore_index=True)
    df.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
