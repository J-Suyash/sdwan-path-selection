"""Tests for the band-row PROPOSAL tool using SYNTHETIC repeatability rows.

All rows here are invented. These tests pin the proposal semantics:
half-range baseline reported alongside the max-deviation-from-median
sensitivity, unflagged outliers retained, flagged cells excluded, and
absent metrics reported as data gaps rather than fabricated.
"""

import pytest

from scripts.propose_cross_engine_bands import per_cell_spreads, propose_rows


def _cell(metric, reps, quality="usable"):
    values = list(reps)
    return {
        "quality": quality,
        "n_runs": len(values),
        f"{metric}_min": min(values),
        f"{metric}_max": max(values),
        # mirrors the real artifacts: {repetition_index: value}
        f"{metric}_per_repetition": {str(i): v for i, v in enumerate(values)},
    }


def test_skewed_cell_reports_both_statistics():
    # Synthetic skewed cell: half-range understates the true max deviation
    # from the median by a factor of two; both must be reported.
    cells = per_cell_spreads([_cell("synthetic_metric", [0.0, 0.0, 0.0, 0.0, 10.0])],
                             "synthetic_metric")
    assert len(cells) == 1
    assert cells[0]["half_range"] == pytest.approx(5.0)
    assert cells[0]["max_dev_from_median"] == pytest.approx(10.0)


def test_unflagged_outlier_retained():
    rows = [
        _cell("synthetic_metric", [1.0, 1.1, 0.9, 1.05, 25.0]),  # usable outlier cell
        _cell("synthetic_metric", [1.0, 1.1, 0.9, 1.05, 1.0]),
    ]
    cells = per_cell_spreads(rows, "synthetic_metric")
    assert len(cells) == 2
    assert max(c["half_range"] for c in cells) == pytest.approx((25.0 - 0.9) / 2.0)


def test_flagged_and_thin_cells_excluded():
    rows = [
        _cell("synthetic_metric", [1.0, 2.0, 3.0], quality="insufficient"),
        _cell("synthetic_metric", [1.0]),  # single run
        _cell("synthetic_metric", [1.0, 2.0]),
    ]
    cells = per_cell_spreads(rows, "synthetic_metric")
    assert len(cells) == 1


def test_absent_metric_is_data_gap_not_fabricated():
    rows = [_cell("present_metric", [1.0, 2.0, 1.5])]
    out_rows, gaps = propose_rows(rows, ["present_metric", "queue_delay_ms"])
    assert [r["metric"] for r in out_rows] == ["present_metric"]
    assert gaps == ["queue_delay_ms"]
    assert out_rows[0]["status"] == "PROPOSED_NOT_ADOPTED"
