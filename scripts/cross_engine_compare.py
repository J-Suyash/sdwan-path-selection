"""Cross-engine distribution comparison (round item 5).

Compares emulator vs Mininet replicate values per metric: medians, p95
tails, KS statistic and Cliff's delta effect size. Acceptance uses the
bands derived from within-engine repeatability
(analysis/cross_engine_thresholds.csv) — no fixed percentage thresholds.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EFFECT_SIZES = (
    (0.147, "negligible"),
    (0.330, "small"),
    (0.474, "medium"),
)


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Cliff's delta: P(a > b) - P(a < b), via pairwise comparison."""

    if len(a) == 0 or len(b) == 0:
        return float("nan")
    greater = sum((x > b).sum() for x in a)
    less = sum((x < b).sum() for x in a)
    return float(greater - less) / (len(a) * len(b))


def effect_label(delta: float) -> str:
    for threshold, label in EFFECT_SIZES:
        if abs(delta) < threshold:
            return label
    return "large"


def compare_metric(emulator: np.ndarray, mininet: np.ndarray) -> dict:
    emulator = np.asarray(emulator, dtype=float)
    mininet = np.asarray(mininet, dtype=float)
    ks = stats.ks_2samp(emulator, mininet)
    delta = cliffs_delta(emulator, mininet)
    return {
        "n_emulator": len(emulator),
        "n_mininet": len(mininet),
        "median_emulator": float(np.median(emulator)),
        "median_mininet": float(np.median(mininet)),
        "median_diff": float(np.median(emulator) - np.median(mininet)),
        "p95_emulator": float(np.percentile(emulator, 95)),
        "p95_mininet": float(np.percentile(mininet, 95)),
        "tail_ratio_p95": float(np.percentile(emulator, 95) / max(np.percentile(mininet, 95), 1e-12)),
        "ks_statistic": float(ks.statistic),
        "ks_pvalue": float(ks.pvalue),
        "cliffs_delta": delta,
        "effect": effect_label(delta),
    }


def decide(result: dict, band: float) -> dict:
    """Accept when |median diff| and p95 tail deviation sit inside the
    within-engine reproducibility band."""

    tail_dev = abs(result["p95_emulator"] - result["p95_mininet"])
    result["band"] = band
    result["accepted"] = bool(
        abs(result["median_diff"]) <= band and tail_dev <= band
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True,
                        help="CSV with columns case, metric, value")
    parser.add_argument("--mininet", type=Path, required=True,
                        help="CSV with columns case, metric, value")
    parser.add_argument("--thresholds", type=Path,
                        default=Path("analysis/cross_engine_thresholds.csv"))
    parser.add_argument("--out", type=Path,
                        default=analysis_default())
    args = parser.parse_args()
    emu = pd.read_csv(args.emulator)
    mini = pd.read_csv(args.mininet)
    bands = pd.read_csv(args.thresholds).set_index("metric")["max_dev_from_median_q90"]

    rows = []
    for (case, metric), group in emu.groupby(["case", "metric"]):
        counterpart = mini[(mini["case"] == case) & (mini["metric"] == metric)]
        if metric not in bands.index:
            raise SystemExit(f"no derived band for metric {metric!r}")
        result = decide(compare_metric(group["value"], counterpart["value"]), bands[metric])
        rows.append({"case": case, "metric": metric, **result})
    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {args.out}; "
          f"{int(out['accepted'].sum())}/{len(out)} metric comparisons accepted")
    return 0


def analysis_default() -> Path:
    return Path("analysis/cross_engine_comparison.csv")


if __name__ == "__main__":
    raise SystemExit(main())
