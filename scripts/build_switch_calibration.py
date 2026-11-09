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
import json
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
        entry = dict(zip(KEY_COLUMNS, key))
        entry["n_runs"] = int(len(group))
        entry["quality"] = "insufficient" if len(group) < min_repeats else "usable"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/switching_calibration.csv"))
    parser.add_argument(
        "--repeatability",
        type=Path,
        default=None,
        help="Optional per-run detail dump for the audit trail.",
    )
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw = read_raw(args.raw)
    rows, repeatability = build_rows(raw, args.min_repeats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.out, index=False)
    print(f"{len(rows)} calibration rows -> {args.out}")
    usable = (rows["quality"] == "usable").sum()
    insufficient = (rows["quality"] == "insufficient").sum()
    print(f"usable {usable}, insufficient {insufficient} (min repeats {args.min_repeats})")
    if args.repeatability:
        args.repeatability.parent.mkdir(parents=True, exist_ok=True)
        args.repeatability.write_text(json.dumps(repeatability, indent=2, default=str))
        print(f"repeatability detail -> {args.repeatability}")
    summary = rows[
        [c for c in KEY_COLUMNS if c in rows.columns]
        + ["n_runs", "quality", "interruption_s_mean", "loss_frac_mean", "reordering_frac_mean"]
    ]
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
