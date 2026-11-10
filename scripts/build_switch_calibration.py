"""Aggregate repeated Mininet switching measurements into calibration rows.

    uv run python scripts/build_switch_calibration.py \
        --raw testbed/outputs/cal_v1_full/switch_metrics_raw.csv \
        --out data/switching_calibration.csv \
        --repeatability testbed/outputs/cal_v1_full/repeatability.json

Reads the raw repeated-run metrics produced by
``testbed.run_switch_calibration``, groups them by the emulator's row key
(old/new RTT, jitters, transport, flow type) plus in-flight and occupancy
buckets, and writes per-group statistics to the calibration file the
``SwitchingModel`` reads via ``SDWanConfig.switching_calibration_path``.
Group sizes below three repetitions stay flagged ``insufficient`` and are
not promoted to calibration rows.

Output fields:
``old_rtt_ms`` etc. like ``data/switching_calibration_template.csv``
plus ``n``, ``interruption_s_mean``, ``..._p95``, loss/reordering means
and inter-repetition coefficients of variation for repeatability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

KEY_COLUMNS = (
    "old_rtt_ms",
    "new_rtt_ms",
    "old_jitter_ms",
    "new_jitter_ms",
    "flow_type",
    "transport",
    "in_flight_bucket",
    "occupancy_bucket",
)

METRIC_COLUMNS = ("interruption_s", "loss_frac", "reordering_frac", "route_update_s")

BUCKET_EDGES = [0.0, 1.5, 10.5, 50.5, np.inf]
BUCKET_LABELS = ("small", "medium", "large", "huge")


def bucket_values(series: pd.Series, edges: list[float], labels: tuple[str, ...]) -> pd.Series:
    return pd.cut(series, bins=edges, labels=labels, right=True)


def with_buckets(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["in_flight_bucket"] = bucket_values(
        frame["packets_in_flight"], BUCKET_EDGES, BUCKET_LABELS
    ).astype(str)
    frame["occupancy_bucket"] = bucket_values(
        frame["queue_occupancy_frac"], [0.0, 0.05, 0.3, 0.8, 1.0001],
        ("empty", "low", "high", "full"),
    ).astype(str)
    return frame


def coefficient_of_variation(values: np.ndarray) -> float:
    """Inter-repetition relative spread; nan when fewer than 2 values."""

    if values.size < 2:
        return float("nan")
    mean = float(np.mean(values))
    if mean <= 0:
        # Fraction metrics: use spread over the largest value instead.
        scale = max(float(np.max(np.abs(values))), 1e-12)
    else:
        scale = mean
    return float(np.std(values, ddof=1) / (scale + 1e-12))


def read_raw(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = with_buckets(frame)
    for column in METRIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def build_rows(raw: pd.DataFrame, min_repeats: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    grouped = raw.groupby(list(KEY_COLUMNS), dropna=False)
    rows, repeatability = [], []
    for key, group in grouped:
        # Drop stall/failure outliers before any statistic: a run whose
        # sent-frames count departs from the group median (connection
        # stall, timeout) otherwise poisons interruption_s.
        if "sent_frames" in group.columns and group["sent_frames"].notna().any():
            nominal = float(group["sent_frames"].median())
            keep = (group["sent_frames"] - nominal).abs() <= 0.2 * max(nominal, 1.0)
            dropped = int((~keep).sum())
            if dropped < len(group):
                group = group[keep]
        else:
            dropped = 0
        entry = dict(zip(KEY_COLUMNS, key))
        entry["n_runs"] = int(len(group))
        entry["runs_dropped_stall"] = dropped
        quality = "usable" if len(group) >= min_repeats else "insufficient"
        entry["quality"] = "trimmed_" + quality if dropped else quality
        for metric in METRIC_COLUMNS:
            values = group[metric].dropna().to_numpy(dtype=float)
            if values.size == 0:
                entry[f"{metric}_mean"] = float("nan")
                entry[f"{metric}_p95"] = float("nan")
                entry[f"{metric}_min"] = float("nan")
                entry[f"{metric}_max"] = float("nan")
                continue
            entry[f"{metric}_mean"] = float(np.mean(values))
            entry[f"{metric}_p95"] = float(np.percentile(values, 95))
            entry[f"{metric}_min"] = float(np.min(values))
            entry[f"{metric}_max"] = float(np.max(values))
            if metric in {"loss_frac", "reordering_frac"}:
                entry[f"{metric}_cv_repetition"] = coefficient_of_variation(np.maximum(values, 1e-9))
            else:
                entry[f"{metric}_cv_repetition"] = coefficient_of_variation(values)
        rows.append(entry)

        repeatability.append(
            {
                **entry,
                **{
                    f"{m}_per_repetition": {
                        str(r): float(v)
                        for r, v in zip(group["repetition"], group[m], strict=False)
                    }
                    for m in METRIC_COLUMNS
                },
            }
        )
    return pd.DataFrame(rows), repeatability


def config_fingerprint(scenario_path: Path, config_tag: str | None) -> str:
    """Hash the scenario definition and queue configuration.

    Rows from incompatible configurations must not share a calibration
    key; the fingerprint partitions them.
    """

    scenario_bytes = scenario_path.read_bytes()
    digest = hashlib.sha256(scenario_bytes).hexdigest()[:16]
    payload = f"{digest}|{config_tag or 'shared'}"
    return payload


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def build_manifest(
    scenario: dict,
    raw: pd.DataFrame,
    rows: pd.DataFrame,
    scenario_path: Path,
    config_tag: str | None,
    min_repeats: int,
    raw_path: Path,
) -> dict:
    """Expected vs observed run matrix, exclusions and traceability."""

    fingerprint = config_fingerprint(scenario_path, config_tag)
    scenario_bytes = scenario_path.read_bytes()
    expected = []
    for index, event in enumerate(scenario["events"]):
        for rep in range(int(scenario.get("repetitions", 1))):
            expected.append(
                {
                    "event_index": index,
                    "repetition": rep,
                    "workload": event["workload"],
                    "old_path": event["old_path"],
                    "new_path": event["new_path"],
                }
            )
    observed = set(
        zip(
            raw["event_index"],
            raw["repetition"],
            raw["workload"],
            raw["old_path"],
            raw["new_path"],
        )
    )
    missing = [
        e for e in expected
        if (e["event_index"], e["repetition"], e["workload"], e["old_path"], e["new_path"])
        not in observed
    ]
    workloads = {event["workload"] for event in scenario["events"]}
    transports = sorted({wl["transport"] for wl in scenario["workloads"].values()})
    directed = {
        (event["old_path"], event["new_path"]) for event in scenario["events"]
    }

    per_key_runs: dict[str, list[str]] = {}
    for key, group in raw.groupby(list(KEY_COLUMNS), dropna=False):
        per_key_runs[str(np.array(key, dtype=object).tolist())] = sorted(
            group["run_id"].tolist()
        )

    dropped = (
        raw.copy()
        if "sent_frames" not in raw.columns
        else _drop_failed_runs(raw)
    )
    exclusions = []
    if "sent_frames" in raw.columns:
        merged = raw.merge(dropped[["run_id"]], on="run_id", how="left", indicator=True)
        exclusions = merged.loc[merged["_merge"] == "left_only", "run_id"].tolist()

    return {
        "config_fingerprint": fingerprint,
        "git_commit": git_commit(),
        "scenario_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
        "queue_limit_packets": scenario.get("queue_limit_packets"),
        "per_path_queue_limit_packets": scenario.get(
            "per_path_queue_limit_packets"
        ),
        "branch_profile": scenario.get("branch_profile"),
        "workload_regime": scenario.get("workload_regime"),
        "transports": transports,
        "directed_transitions": sorted(f"{a}->{b}" for a, b in directed),
        "expected_runs": len(expected),
        "observed_runs": int(raw["run_id"].nunique()),
        "missing_runs": missing,
        "excluded_runs": exclusions,
        "workloads": sorted(workloads),
        "min_repeats_required": min_repeats,
        "aggregate_traceability": per_key_runs,
    }


def _drop_failed_runs(raw: pd.DataFrame) -> pd.DataFrame:
    keep_parts = []
    for _, group in raw.groupby(list(KEY_COLUMNS), dropna=False):
        if group["sent_frames"].notna().any():
            nominal = float(group["sent_frames"].median())
            keep = (group["sent_frames"] - nominal).abs() <= 0.2 * max(
                nominal, 1.0
            )
            if keep.any():
                group = group[keep]
        keep_parts.append(group)
    return pd.concat(keep_parts, ignore_index=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("testbed/outputs/calibration_stats.csv"))
    parser.add_argument(
        "--expanded",
        type=Path,
        default=None,
        help="Optional per-run rows in the emulator calibration schema "
        "(data/switching_calibration_template.csv); usable by SwitchingModel.",
    )
    parser.add_argument(
        "--repeatability",
        type=Path,
        default=None,
        help="Optional per-run detail dump for the audit trail.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional JSON manifest with expected/observed runs and "
        "config fingerprint (spec section 4).",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=None,
        required=False,
        help="Scenario JSON the raw sweep was generated from (required "
        "with --manifest).",
    )
    parser.add_argument(
        "--config-tag",
        type=str,
        default=None,
        help="Queue configuration tag the sweep used, e.g. "
        "shared_1000pkt vs per_path_v1.",
    )
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser.parse_args()


def build_expanded(raw: pd.DataFrame, min_repeats: int) -> pd.DataFrame:
    """Per-run rows after stall trimming, in SwitchingModel's schema."""

    if "sent_frames" in raw.columns:
        # Trim per key group with the same rule as the statistics rows.
        trimmed = []
        for _, group in raw.groupby(list(KEY_COLUMNS), dropna=False):
            if group["sent_frames"].notna().any():
                nominal = float(group["sent_frames"].median())
                keep = (group["sent_frames"] - nominal).abs() <= 0.2 * max(nominal, 1.0)
                if keep.any() and not keep.all():
                    group = group[keep]
            trimmed.append(group)
        raw = pd.concat(trimmed, ignore_index=True)
    columns = list(
        REQUIRED := {
            "old_rtt_ms",
            "new_rtt_ms",
            "old_jitter_ms",
            "new_jitter_ms",
            "packets_in_flight",
            "flow_type",
            "transport",
            "queue_occupancy_frac",
            "interruption_s",
            "loss_frac",
            "reordering_frac",
        }
    )
    out = raw[[c for c in columns if c in raw.columns]].copy()
    if "run_id" in raw.columns:
        out.insert(0, "run_id", raw["run_id"])
    return out


def main() -> None:
    args = parse_args()
    raw = read_raw(args.raw)
    rows, repeatability = build_rows(raw, args.min_repeats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.out, index=False)
    print(f"{len(rows)} calibration statistics rows -> {args.out}")
    usable = (rows["quality"].str.startswith("usable")).sum()
    trimmed = (rows["quality"].str.startswith("trimmed_usable")).sum()
    insufficient = (rows["quality"] == "insufficient").sum()
    print(f"usable {usable} (trimmed {trimmed}), insufficient {insufficient} (min repeats {args.min_repeats})")
    if args.repeatability:
        args.repeatability.parent.mkdir(parents=True, exist_ok=True)
        args.repeatability.write_text(json.dumps(repeatability, indent=2, default=str))
        print(f"repeatability detail -> {args.repeatability}")
    if args.manifest:
        if args.scenario is None:
            raise SystemExit("--manifest requires --scenario")
        import json as _json

        manifest = build_manifest(
            _json.loads(args.scenario.read_text()),
            raw,
            rows,
            args.scenario,
            args.config_tag,
            args.min_repeats,
            args.raw,
        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(_json.dumps(manifest, indent=2, default=str))
        print(f"manifest -> {args.manifest}")
    if args.expanded:
        expanded = build_expanded(raw, args.min_repeats)
        args.expanded.parent.mkdir(parents=True, exist_ok=True)
        expanded.to_csv(args.expanded, index=False)
        print(f"{len(expanded)} per-run rows -> {args.expanded}")
    summary = rows[
        [c for c in KEY_COLUMNS if c in rows.columns]
        + ["n_runs", "quality", "interruption_s_mean", "loss_frac_mean", "reordering_frac_mean"]
    ]
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
