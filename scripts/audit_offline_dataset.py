"""Audit transition provenance, support and split leakage before offline RL."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import pandas as pd

# Repo-local import (offline.ope) without requiring PYTHONPATH: the repo
# is a flat tree, not a package, so a bare `python scripts/audit_...`
# from the repo root must still find it (mirrors conftest.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline.ope import support_report

REQUIRED = {
    "obs",
    "next_obs",
    "action",
    "reward",
    "policy",
    "episode",
    "t",
    "behavior_action_prob",
    "workload_profile",
    "workload_regime",
    "seed",
    "policy_version",
    "simulator_version",
}


def audit(path: str, n_actions: int = 81) -> dict:
    files = sorted(glob.glob(str(Path(path) / "**" / "*.parquet"), recursive=True))
    if not files:
        raise FileNotFoundError(f"no parquet files below {path}")
    frame = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        raise ValueError(f"missing transition metadata: {missing}")
    if frame[["seed", "episode", "t"]].duplicated().any():
        raise ValueError("duplicate seed/episode/t rows would make splits ambiguous")
    probs = frame["behavior_action_prob"].to_numpy(float)
    if ((probs <= 0) | (probs > 1)).any():
        raise ValueError("behavior_action_prob must be in (0, 1]")
    by_regime = frame.groupby(
        ["workload_profile", "workload_regime", "simulator_version"], dropna=False
    )
    return {
        "rows": len(frame),
        "files": len(files),
        "episodes": int(
            frame[["policy", "episode", "seed"]].drop_duplicates().shape[0]
        ),
        "profiles": sorted(frame["workload_profile"].unique().tolist()),
        "support": support_report(frame, n_actions),
        "regime_rows": {
            "|".join(map(str, key if isinstance(key, tuple) else (key,))): len(group)
            for key, group in by_regime
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default="data/datasets", nargs="?")
    parser.add_argument("--actions", type=int, default=81)
    args = parser.parse_args()
    print(json.dumps(audit(args.path, args.actions), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
