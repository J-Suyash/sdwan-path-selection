#!/usr/bin/env python3
"""PROPOSAL TOOL: derive candidate cross-engine band rows for additional
metrics from within-engine repeatability artifacts. NOT adopted bands.

This extends the rule of scripts/derive_cross_engine_thresholds.py to a
parameterized metric set and reports BOTH spread statistics side by side:

* cell half-range (max - min) / 2  - the historical baseline statistic
* true max deviation from the cell median - the sensitivity statistic,
  computable from the stored ``<metric>_per_repetition`` values

Rows not flagged ``insufficient`` are retained as-is, including unflagged
outlier replicates. Whether half-range or max-deviation is the appropriate
reproducibility statistic remains an owner research decision; this tool
reports both and adopts neither.

Every emitted row is marked status=PROPOSED_NOT_ADOPTED. A requested metric
whose statistics are absent from the repeatability artifacts is reported
as a DATA GAP - no row is fabricated for it.

Usage:
    uv run python scripts/propose_cross_engine_bands.py \
        --repeatability testbed/outputs/cal_v1_full/repeatability.json \
        [--repeatability testbed/outputs/cal_v2_perpath/repeatability.json] \
        --metrics delay_median_ms,jitter_mean_ms,throughput_mbps,queue_delay_ms \
        --out analysis/cross_engine_thresholds_proposal_draft.csv
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Metrics the cross-engine case manifest requests that have no committed
# band row. queue_delay_ms additionally has no adopted estimator.
DEFAULT_METRICS = (
    "delay_median_ms",
    "jitter_mean_ms",
    "throughput_mbps",
    "queue_delay_ms",
)


def per_cell_spreads(rows: list[dict], metric: str) -> list[dict]:
    """Per-cell spread statistics for one metric.

    Returns one dict per retained cell with keys ``half_range`` and
    ``max_dev_from_median`` (the latter None when per-repetition values
    are absent). Cells flagged ``insufficient`` or with fewer than two
    runs are excluded; every other replicate is retained, including
    unflagged outliers.
    """

    min_key, max_key = f"{metric}_min", f"{metric}_max"
    rep_key = f"{metric}_per_repetition"
    cells = []
    for row in rows:
        if row.get("quality") == "insufficient" or row.get("n_runs", 0) < 2:
            continue
        lo, hi = row.get(min_key), row.get(max_key)
        reps = row.get(rep_key)
        if lo is None or hi is None or pd.isna(lo) or pd.isna(hi):
            if not reps:
                continue
        cell = {}
        if lo is not None and hi is not None and pd.notna(lo) and pd.notna(hi):
            cell["half_range"] = max(float(hi) - float(lo), 0.0) / 2.0
        if reps:
            # stored as {repetition_index: value}
            values = np.asarray(list(reps.values()), dtype=float)
            med = float(np.median(values))
            cell["max_dev_from_median"] = float(np.max(np.abs(values - med)))
        if cell:
            cell["n_runs"] = int(row.get("n_runs", 0))
            cells.append(cell)
    return cells


def propose_rows(rows: list[dict], metrics) -> tuple[list[dict], list[str]]:
    """Build proposal rows; returns (rows, data_gap_metrics)."""

    out_rows, gaps = [], []
    for metric in metrics:
        cells = per_cell_spreads(rows, metric)
        if not cells:
            gaps.append(metric)
            continue
        half = np.asarray([c["half_range"] for c in cells if "half_range" in c])
        devs = np.asarray(
            [c["max_dev_from_median"] for c in cells if "max_dev_from_median" in c]
        )
        record = {
            "metric": metric,
            "cells_used": len(cells),
            "replicates_per_cell_min": min(c["n_runs"] for c in cells),
            "status": "PROPOSED_NOT_ADOPTED",
            "band_rule": (
                "PROPOSAL: accept emulator/Mininet |difference| <= q90 of "
                "within-engine per-cell spread; half-range is the historical "
                "baseline, max-deviation-from-median reported as sensitivity; "
                "owner decision pending"
            ),
        }
        if half.size:
            record["cell_half_range_median"] = float(np.median(half))
            record["cell_half_range_q90"] = float(np.quantile(half, 0.9))
            record["cell_half_range_q95"] = float(np.quantile(half, 0.95))
        if devs.size:
            record["max_dev_from_median_median"] = float(np.median(devs))
            record["max_dev_from_median_q90"] = float(np.quantile(devs, 0.9))
            record["max_dev_from_median_q95"] = float(np.quantile(devs, 0.95))
        out_rows.append(record)
    return out_rows, gaps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeatability", type=Path, action="append", required=True)
    parser.add_argument("--metrics", type=str, default=",".join(DEFAULT_METRICS))
    parser.add_argument("--out", type=Path,
                        default=Path("analysis/cross_engine_thresholds_proposal_draft.csv"))
    args = parser.parse_args()

    rows: list[dict] = []
    for path in args.repeatability:
        rows.extend(json.loads(path.read_text()))

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    out_rows, gaps = propose_rows(rows, metrics)

    frame = pd.DataFrame(out_rows)
    frame.to_csv(args.out, index=False)
    print(frame.to_string(index=False) if out_rows else "(no proposal rows)")
    print(f"\nwrote {args.out}")
    for metric in gaps:
        print(
            f"DATA GAP: {metric}: no per-cell replicate statistics in the "
            "supplied repeatability artifacts; no row proposed"
        )


if __name__ == "__main__":
    main()
