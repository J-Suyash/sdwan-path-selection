"""Derive cross-engine acceptance thresholds from measured repeatability
(verification round item 5).

Rule: the acceptable emulator/Mininet difference for a metric is bounded
by the *within-engine* reproducibility of the same measurement. We take
the calibration sweeps' per-cell replicate spread and use its q90 across
cells as the band. No fixed percentage thresholds are invented.

Statistic naming (corrected): this script computes the per-cell spread
as the *half-range* ``(max - min) / 2`` from the stored per-cell
extremes. The half-range equals the maximum deviation from the midrange,
but it is NOT the maximum deviation from the median: for skewed
replicates such as [0, 0, 0, 0, 10] the median is 0 and the true maximum
deviation from the median is 10, while the half-range is 5. The
half-range can therefore understate that quantity by up to a factor of
two. (The repeatability JSON also stores ``<metric>_per_repetition``
values per cell, so the true maximum deviation from the median is
computable from the same artifacts; this script retains its historical
min/max-based computation.) Whether the half-range or the true maximum
deviation from the cell median is the appropriate reproducibility
statistic is a research decision for the owner; this script only reports
the half-range it has always computed, now under an honest name.

    uv run python scripts/derive_cross_engine_thresholds.py \
        --repeatability testbed/outputs/cal_v1_full/repeatability.json \
        [--repeatability testbed/outputs/cal_v2_perpath/repeatability.json] \
        --out analysis/cross_engine_thresholds.csv
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = {
    "interruption_s": ["interruption_s_mean", "interruption_s_min", "interruption_s_max"],
    "loss_frac": ["loss_frac_mean", "loss_frac_min", "loss_frac_max"],
    "reordering_frac": ["reordering_frac_mean", "reordering_frac_min", "reordering_frac_max"],
}


def per_cell_max_deviation(rows: list[dict], columns: list[str]) -> dict[str, list[float]]:
    """Per-cell half-range (max - min) / 2 per cell per metric.

    The spread is reconstructed from the stored per-cell extremes.
    This is the half-range, not the maximum deviation from the median;
    see the module docstring for the skewed-replicate caveat and the
    available per-repetition values. The name of this function is
    retained for import compatibility.
    """

    deviations: dict[str, list[float]] = {name: [] for name in METRICS}
    cells = 0
    for row in rows:
        if row.get("quality") == "insufficient" or row.get("n_runs", 0) < 2:
            continue
        cells += 1
        for metric, cols in METRICS.items():
            lo, hi = row[cols[1]], row[cols[2]]
            if pd.notna(lo) and pd.notna(hi):
                deviations[metric].append(max(float(hi) - float(lo), 0.0) / 2.0)
    return deviations, cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeatability", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, default=Path("analysis/cross_engine_thresholds.csv"))
    args = parser.parse_args()

    rows: list[dict] = []
    for path in args.repeatability:
        rows.extend(json.loads(path.read_text()))
    deviations, cells = per_cell_max_deviation(rows, METRICS)

    out_rows = []
    for metric, values in deviations.items():
        arr = np.asarray(values, dtype=float)
        if arr.size == 0:
            continue
        out_rows.append(
            {
                "metric": metric,
                "cells_used": cells,
                "replicates_per_cell_min": int(min(r.get("n_runs", 0) for r in rows if r.get("quality") != "insufficient")),
                "cell_half_range_median": float(np.median(arr)),
                "cell_half_range_q90": float(np.quantile(arr, 0.9)),
                "cell_half_range_q95": float(np.quantile(arr, 0.95)),
                "band_rule": "accept emulator/Mininet |difference| <= q90 of within-engine per-cell half-range (max-min)/2",
            }
        )
    frame = pd.DataFrame(out_rows)
    frame.to_csv(args.out, index=False)
    print(frame.to_string(index=False))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
