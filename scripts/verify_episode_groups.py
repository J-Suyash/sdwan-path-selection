"""Verify train/validation/test episode groups are disjoint (round item 6).

Datasets carry a leakage-safe ``split_group`` key per episode (profile,
regime, seed, trace window). This tool checks that any assigned
partition of episodes leaves no group in two partitions, and that every
episode has a partition assignment.

    uv run python scripts/verify_episode_groups.py \
        --manifest data/datasets/manifest.csv \
        --assignment data/datasets/split_assignment.json

The assignment JSON maps split_group values (or their sha256 digests)
to one of train/validation/test.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


def check_disjointness(manifest: pd.DataFrame, assignment: dict[str, str]) -> dict:
    """Return a report; raises ValueError on any violation."""

    if "split_group" not in manifest.columns:
        raise ValueError("manifest has no split_group column")

    def key_of(group: str) -> str:
        # Assignment may key groups directly or by sha256 of the group
        # string. Both forms present with conflicting partitions is an
        # error: it must never silently resolve to one of them.
        digest = hashlib.sha256(group.encode()).hexdigest()
        direct = assignment.get(group)
        digested = assignment.get(digest)
        if direct is not None and digested is not None and direct != digested:
            raise ValueError(
                f"conflicting partition entries for group {group!r}: "
                f"{direct!r} vs {digested!r}"
            )
        if direct is not None:
            return group
        if digested is not None:
            return digest
        raise ValueError(f"split_group has no partition assignment: {group}")

    group_rows: dict[str, set[str]] = {}
    for _, row in manifest.iterrows():
        group = str(row["split_group"])
        group_rows.setdefault(key_of(group), set()).add(group)

    overlaps: dict[str, list[str]] = {}
    for a_key, groups in group_rows.items():
        part = assignment[a_key]
        overlaps.setdefault(part, []).extend(groups)

    report = {
        "episodes": len(manifest),
        "distinct_groups": len(group_rows),
        "partitions": {
            part: {"groups": len(gs), "episodes": int(
                (manifest["split_group"].isin(gs)).sum()
            )}
            for part, gs in overlaps.items()
        },
        "overlaps": [],
    }
    parts = list(overlaps)
    for i, p1 in enumerate(parts):
        for p2 in parts[i + 1:]:
            shared = set(overlaps[p1]) & set(overlaps[p2])
            if shared:
                report["overlaps"].append(
                    {"partitions": [p1, p2], "groups": sorted(shared)}
                )
    if report["overlaps"]:
        raise ValueError(f"split groups appear in multiple partitions: {report['overlaps']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    args = parser.parse_args()
    manifest = pd.read_csv(args.manifest)
    assignment = json.loads(args.assignment.read_text())
    report = check_disjointness(manifest, assignment)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
