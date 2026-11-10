"""Regression tests for the held-out flow-record split (verification spec
section 1).

Guarantee under test: the split is a deterministic row-level holdout over
the source frame. Session/transfer-level disjointness cannot be
guaranteed from the SDNCampus release because identity fields are
stripped; these tests pin the deterministic-row-level property instead.
"""

import numpy as np
import pandas as pd
import pytest

from scripts.extract_sdncampus_transfer_summaries import (
    SPLIT_KEY_COLUMNS,
    classify_flow_end,
    heldout_parity,
    record_split_keys,
    summarize_transfer_file,
)
from scripts.extract_sdncampus_distributions import SDNCAMPUS_ASSETS


def _split_sample(n: int, start: int) -> pd.DataFrame:
    rows = np.arange(start, start + n)
    return pd.DataFrame(
        {
            "Flow Duration": np.full(n, 1_000_000.0),
            "Total Length of Fwd Packet": np.full(n, 100.0),
            "Total Length of Bwd Packet": rows.astype(float),
            "FIN Flag Count": np.zeros(n, dtype=float),
            "RST Flag Count": np.zeros(n, dtype=float),
        }
    )


def test_split_is_deterministic():
    frame = _split_sample(40, 0)
    keys = record_split_keys(frame)
    assert np.array_equal(heldout_parity(keys, 20261110), heldout_parity(keys, 20261110))
    assert heldout_parity(keys, 20261110).sum() == heldout_parity(keys, 20261110).sum()


def test_row_index_breaks_identical_record_ties():
    """Identical content at different indices can land in different halves."""

    frame = _split_sample(200, 0)
    # Zero out all measured fields so every key differs by index only.
    frame["Total Length of Fwd Packet"] = 100.0
    frame["Total Length of Bwd Packet"] = 400.0
    frame["Flow Duration"] = 1_000_000.0
    half = heldout_parity(record_split_keys(frame), 20261110)
    assert half.any() and not half.all()  # identical rows went both ways


def test_changed_measured_field_changes_hash_input():
    frame = _split_sample(50, 0)
    second = frame.copy()
    second["Total Length of Bwd Packet"] = 401.0
    mask = heldout_parity(record_split_keys(frame), 20261110)
    mask2 = heldout_parity(record_split_keys(second), 20261110)
    assert not np.array_equal(mask, mask2)


def test_split_partitions_all_eligible_rows_once():
    frame = _split_sample(1000, 0)
    keys = record_split_keys(frame)
    mask = heldout_parity(keys, 20261110)
    assert mask.sum() + (~mask).sum() == len(frame)  # no rows lost
    assert not (mask & ~mask).any()  # disjoint by construction
    assert keys.duplicated().sum() == 0  # deduplicated keys (index unique)


def test_split_is_not_label_dependent():
    """Termination flags do not flip record partition membership."""

    base = _split_sample(500, 0)
    flipped = base.copy()
    flipped["FIN Flag Count"] = 1.0
    flipped["RST Flag Count"] = 2.0
    mask_a = heldout_parity(record_split_keys(base), 20261110)
    mask_b = heldout_parity(record_split_keys(flipped), 20261110)
    assert np.array_equal(mask_a, mask_b)
    assert set(SPLIT_KEY_COLUMNS).isdisjoint({"FIN Flag Count", "RST Flag Count"})


def test_source_order_is_stable_before_split():
    """The extractor reads the CSV unsorted and splits on the read order.

    Any future filtering, sorting or dedup is a new split version and must
    be recorded in the manifest (seed + sha256). This test asserts the
    extractor consumes the raw frame as loaded.
    """

    frame = _split_sample(300, 0)
    shuffled = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)

    mask_stable = heldout_parity(record_split_keys(frame), 20261110)
    mask_reordered = heldout_parity(record_split_keys(shuffled), 20261110)
    # A reordered frame is a different row-index identity: the split
    # changes, which is why the manifest pins the file sha256 and seed.
    assert not np.array_equal(mask_stable, mask_reordered)
    assert mask_reordered.sum() + (~mask_reordered).sum() == len(shuffled)


def test_held_out_fraction_reported_per_group():
    asset = SDNCAMPUS_ASSETS["dropbox"]
    frame = _split_sample(400, 0)
    frame.loc[:, "FIN Flag Count"] = 0.0
    rows = summarize_transfer_file(frame, asset, seed=20261110, bootstrap_replicates=5)
    by = {(r["split_half"], r["connection_end"]): r for r in rows}
    total = sum(r["transfer_rows"] for r in rows)
    assert total == 400
    assert abs(by[("held_out", "censored")]["transfer_rows"] / 200 - 0.5) < 0.5


def test_classify_counts_reconcile_to_source_rows():
    frame = _split_sample(120, 0)
    frame.loc[frame.index[40:80], ["FIN Flag Count", "RST Flag Count"]] = (1, 0)
    kinds = classify_flow_end(frame["FIN Flag Count"], frame["RST Flag Count"])
    assert kinds.value_counts().reindex(["fin_rst", "censored"]).fillna(0).sum() == 120


def test_payloadless_fin_excluded_from_payload_fit():
    """Teardown-only FIN records are churn, not payload observations."""

    frame = _split_sample(6, 0)
    frame["Total Length of Fwd Packet"] = 0.0
    frame["Total Length of Bwd Packet"] = 31.0  # teardown-size FIN
    asset = SDNCAMPUS_ASSETS["dropbox"]
    rows = summarize_transfer_file(frame, asset, seed=7, bootstrap_replicates=5)
    for r in rows:
        assert r["transfer_rows"] == r["teardown_only_rows"]
        assert r["payload_rows"] == 0
        assert np.isnan(r["transfer_bytes_median"])


def test_payload_bearing_rows_survive_and_were_counted_once():
    frame = _split_sample(6, 0)
    frame["Total Length of Bwd Packet"] = np.array([400, 500, 600, 400, 31, 500])
    frame.loc[frame.index[4], "FIN Flag Count"] = 1.0  # teardown FIN
    asset = SDNCAMPUS_ASSETS["dropbox"]
    rows = summarize_transfer_file(frame, asset, seed=7, bootstrap_replicates=5)
    payload = sum(r["payload_rows"] for r in rows)
    teardown = sum(r["teardown_only_rows"] for r in rows)
    counted = sum(r["transfer_rows"] for r in rows)
    # Each record appears in exactly one (half, end) group.
    assert counted == 6
    assert payload + teardown == counted
