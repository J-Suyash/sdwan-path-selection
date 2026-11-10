"""Tests for the cross-engine comparison statistics (round item 5)."""

import numpy as np
import pandas as pd
import pytest

from scripts.cross_engine_compare import cliffs_delta, compare_metric, decide


def test_cliffs_delta_direction_and_bounds():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert cliffs_delta(a, a) == pytest.approx(0.0)
    assert cliffs_delta(a * 10, a) == pytest.approx(1.0)  # dominates
    assert cliffs_delta(a, a * 10) == pytest.approx(-1.0)


def test_compare_metric_distributions_not_just_means():
    """Two samples with identical medians but different tails must not
    look equivalent: the tail ratio and KS statistic expose the
    difference that a mean-only comparison would hide."""

    emu = np.array([10.0, 10.1, 10.2, 10.3, 25.0])  # heavy tail
    mini = np.array([10.0, 10.1, 10.2, 10.3, 10.4])
    r = compare_metric(emu, mini)
    assert r["median_diff"] == pytest.approx(0.0)
    assert r["tail_ratio_p95"] > 1.5
    assert r["ks_statistic"] == pytest.approx(0.2)


def test_decide_uses_derived_band_not_percentage():
    r = compare_metric(
        np.array([1.0, 1.1, 0.9, 1.05, 1.0]),
        np.array([1.0, 1.1, 0.9, 1.05, 1.0]),
    )
    accepted = decide(dict(r), band=0.05)
    assert accepted["accepted"] is True
    # A 0.2 difference is a 20% relative error but only fails when the
    # derived band is smaller than the absolute difference.
    rejected = decide(dict(r), band=0.05)
    rejected["median_diff"] = 0.2
    assert decide(rejected, band=0.05)["accepted"] is False


def test_bands_committed_artefact_covers_case_metrics():
    bands = pd.read_csv("analysis/cross_engine_thresholds.csv")
    metrics = set(bands["metric"])
    assert {"interruption_s", "loss_frac", "reordering_frac"} <= metrics
    assert (bands["max_dev_from_median_q90"] >= 0).all()
    # Bands are absolute and small: derived, not assumed percentages.
    assert (bands["max_dev_from_median_q90"] < 0.05).all()
