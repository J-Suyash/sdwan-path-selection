"""Cross-engine distribution comparison (round item 5).

Compares emulator vs Mininet replicate values per metric: medians, p95
tails, KS statistic and Cliff's delta effect size. Acceptance uses the
bands derived from within-engine repeatability
(analysis/cross_engine_thresholds.csv) — no fixed percentage thresholds.

Exit codes:
  0  valid input; report written (report mode) or all comparisons
     accepted (--check mode)
  1  --check mode: at least one comparison rejected under the current
     bands
  2  invalid input or output write failure

Neither mode is whole-round scientific acceptance. --check only gates
the supplied paired tables against the current bands; it does not
verify expected case coverage, replicate adequacy,
configuration/trace provenance, or owner review.
"""

from __future__ import annotations

import json

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EFFECT_SIZES = (
    (0.147, "negligible"),
    (0.330, "small"),
    (0.474, "medium"),
)

REQUIRED_COLUMNS = ("case", "metric", "value")
# Band column preference: the honest name first, the legacy misnamed
# `max_dev_from_median_q90` (used by the committed thresholds CSV) as a
# backward-compatible fallback. Both name the same per-cell spread value.
BAND_COLUMN_CANDIDATES = ("cell_half_range_q90", "max_dev_from_median_q90")
THRESHOLD_COLUMNS = ("metric",)


class InputError(Exception):
    """A known, user-facing input problem (bad file, columns, values)."""


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


def _load_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot read {label} table {path}: {exc}") from None


def _check_identifiers(table: pd.DataFrame, label: str, path: Path) -> None:
    for col in ("case", "metric"):
        series = table[col]
        if series.isna().any():
            row = int(series.index[series.isna()][0]) + 2  # +header, 1-based
            raise InputError(
                f"{label} table {path}: null {col!r} identifier at CSV row {row}")
        blank = series.astype(str).str.strip() == ""
        if blank.any():
            row = int(series.index[blank][0]) + 2
            raise InputError(
                f"{label} table {path}: empty {col!r} identifier at CSV row {row}")


def _check_coverage_sidecar(path: Path, label: str) -> None:
    """Refuse matched-run tables whose harness coverage is incomplete.

    The matched-run harness (scripts/run_emulator_matched_case.py) writes a
    coverage.json beside its numeric CSV. The comparator reads only
    (case, metric, value) and would otherwise accept a partial result as
    complete case evidence, so when the sidecar reports unsupported
    required metrics the load fails closed.
    """

    sidecar = Path(path).with_name("coverage.json")
    if not sidecar.exists():
        return
    try:
        coverage = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(
            f"{label} table {path}: unreadable coverage sidecar {sidecar}: {exc}"
        ) from None
    required = coverage.get("required_metrics")
    if not isinstance(required, dict):
        return
    unsupported = sorted(
        metric
        for metric, entry in required.items()
        if isinstance(entry, dict) and entry.get("status") != "expressible"
    )
    if unsupported:
        raise InputError(
            f"{label} table {path}: matched-run coverage incomplete; "
            f"unsupported required metrics {unsupported} (see {sidecar}); "
            "partial results are not complete case evidence"
        )


def _load_table(path: Path, label: str) -> pd.DataFrame:
    """Read and validate one long-format result table."""

    table = _load_csv(path, label)
    _check_coverage_sidecar(path, label)
    missing = [col for col in REQUIRED_COLUMNS if col not in table.columns]
    if missing:
        raise InputError(
            f"{label} table {path} is missing required columns: {', '.join(missing)}")
    if table.empty:
        raise InputError(f"{label} table {path} has no data rows")
    _check_identifiers(table, label, path)
    try:
        values = pd.to_numeric(table["value"], errors="raise")
    except (TypeError, ValueError):
        raise InputError(
            f"{label} table {path}: 'value' column contains non-numeric entries") from None
    values = values.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise InputError(
            f"{label} table {path}: 'value' column contains non-finite numbers")
    table = table.copy()
    table["value"] = values
    return table


def _resolve_band_column(table: "pd.DataFrame", path: Path) -> str:
    """Pick the band column: honest name preferred, legacy name accepted."""

    for candidate in BAND_COLUMN_CANDIDATES:
        if candidate in table.columns:
            return candidate
    raise InputError(
        f"thresholds table {path} is missing required columns: "
        f"cell_half_range_q90 (or legacy max_dev_from_median_q90)")


def _load_thresholds(path: Path) -> dict:
    """Read and validate the per-metric deviation bands."""

    table = _load_csv(path, "thresholds")
    missing = [col for col in THRESHOLD_COLUMNS if col not in table.columns]
    if missing:
        raise InputError(
            f"thresholds table {path} is missing required columns: {', '.join(missing)}")
    if table.empty:
        raise InputError(f"thresholds table {path} has no data rows")

    metric = table["metric"]
    if metric.isna().any():
        raise InputError(f"thresholds table {path}: null metric name")
    if (metric.astype(str).str.strip() == "").any():
        raise InputError(f"thresholds table {path}: empty metric name")
    duplicated = metric[metric.duplicated()].unique().tolist()
    if duplicated:
        raise InputError(
            f"thresholds table {path}: duplicate metric names: {duplicated[:5]}")
    band_column = _resolve_band_column(table, path)
    try:
        bands = pd.to_numeric(table[band_column], errors="raise")
    except (TypeError, ValueError):
        raise InputError(
            f"thresholds table {path}: '{band_column}' column "
            "contains non-numeric entries") from None
    bands = bands.to_numpy(dtype=float)
    if not np.isfinite(bands).all():
        raise InputError(
            f"thresholds table {path}: '{band_column}' contains "
            "non-finite numbers")
    if (bands < 0).any():
        raise InputError(
            f"thresholds table {path}: '{band_column}' contains "
            "negative bands")
    return dict(zip(metric.tolist(), map(float, bands)))


def _build_groups(table: pd.DataFrame) -> dict:
    """Map (case, metric) -> list of validated numeric values."""

    groups: dict = {}
    for case, metric, value in zip(table["case"], table["metric"], table["value"]):
        groups.setdefault((case, metric), []).append(value)
    return groups


def _format_keys(keys) -> str:
    keys = list(keys)
    if not keys:
        return "none"
    shown = [f"({case!r}, {metric!r})" for case, metric in keys[:5]]
    suffix = "" if len(keys) <= 5 else f" (+{len(keys) - 5} more)"
    return ", ".join(shown) + suffix


def _validate_pairs(emu: pd.DataFrame, mini: pd.DataFrame,
                    thresholds: dict) -> tuple[dict, dict]:
    """Validate cross-table key equality and band coverage. Returns the
    per-engine (case, metric) groups; rows are computed only afterwards."""

    emu_groups = _build_groups(emu)
    mini_groups = _build_groups(mini)
    if emu_groups.keys() != mini_groups.keys():
        only_emu = sorted(emu_groups.keys() - mini_groups.keys(), key=str)
        only_mini = sorted(mini_groups.keys() - emu_groups.keys(), key=str)
        raise InputError(
            "emulator and Mininet tables must contain exactly the same "
            "(case, metric) keys; missing in Mininet: "
            f"{_format_keys(only_emu)}; missing in emulator: "
            f"{_format_keys(only_mini)}")

    table_metrics = {metric for _, metric in emu_groups}
    missing_bands = sorted(table_metrics - thresholds.keys(), key=str)
    if missing_bands:
        raise InputError(
            "no derived band for metric(s): " + _format_keys(
                [(metric, "") for metric in missing_bands]))
    return emu_groups, mini_groups


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "--check only gates the supplied paired tables against the "
            "current bands. It does not verify expected case coverage, "
            "replicate adequacy, configuration/trace provenance, or owner "
            "review. Neither report mode nor check mode is whole-round "
            "scientific acceptance.\n\n"
            "exit codes:\n"
            "  0  valid input; report written (report mode) or all\n"
            "     comparisons accepted (--check mode)\n"
            "  1  --check mode: at least one comparison rejected\n"
            "  2  invalid input or output write failure\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--emulator", type=Path, required=True,
                        help="CSV with columns case, metric, value")
    parser.add_argument("--mininet", type=Path, required=True,
                        help="CSV with columns case, metric, value")
    parser.add_argument("--thresholds", type=Path,
                        default=Path("analysis/cross_engine_thresholds.csv"))
    parser.add_argument("--out", type=Path,
                        default=analysis_default())
    parser.add_argument("--check", action="store_true",
                        help="gate the supplied paired tables: exit 1 if any "
                             "comparison is rejected, 0 if all accepted "
                             "(default: report only, exit 0 for valid tables)")
    return parser.parse_args()


def _write_output(out: pd.DataFrame, path: Path) -> None:
    csv_text = out.to_csv(index=False)
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(csv_text)
    except OSError as exc:
        raise InputError(f"cannot write result CSV {path}: {exc}") from None


def main() -> int:
    args = _parse_args()
    try:
        emu = _load_table(args.emulator, "emulator")
        mini = _load_table(args.mininet, "mininet")
        bands = _load_thresholds(args.thresholds)
        emu_groups, mini_groups = _validate_pairs(emu, mini, bands)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rows = []
    for key in sorted(emu_groups, key=lambda k: (str(k[0]), str(k[1]))):
        case, metric = key
        result = decide(compare_metric(emu_groups[key], mini_groups[key]),
                        bands[metric])
        rows.append({"case": case, "metric": metric, **result})
    out = pd.DataFrame(rows)

    try:
        _write_output(out, args.out)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    accepted = int(out["accepted"].sum())
    total = len(out)
    print(out.to_string(index=False))
    print(f"\nwrote {args.out}; "
          f"{accepted}/{total} metric comparisons accepted")

    if args.check:
        verdict = "CHECK PASSED" if accepted == total else "CHECK FAILED"
        print(f"VERDICT ({verdict}): --check gated the supplied paired tables "
              f"against the current bands ({accepted}/{total} accepted). "
              "This is not whole-round scientific acceptance and does not "
              "cover expected case coverage, replicate adequacy, "
              "provenance, or owner review.")
        return 0 if accepted == total else 1

    print(f"VERDICT (REPORT ONLY): report written; exit code is 0 for valid "
          f"tables even though {total - accepted} comparison(s) were rejected. "
          "This is not whole-round scientific acceptance and does not cover "
          "expected case coverage, replicate adequacy, provenance, or owner "
          "review.")
    return 0


def analysis_default() -> Path:
    return Path("analysis/cross_engine_comparison.csv")


if __name__ == "__main__":
    raise SystemExit(main())
