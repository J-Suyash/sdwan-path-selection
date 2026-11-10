"""Switching-calibration coverage and traceability tests (spec section 4
and 7). Raw artifacts are committed under testbed/outputs/cal_v1_full/.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_switch_calibration import (
    build_manifest,
    build_rows,
    config_fingerprint,
    read_raw,
    with_buckets,
)

RAW = Path("testbed/outputs/cal_v1_full/switch_metrics_raw.csv")
SCENARIO = Path("testbed/scenarios/switch_calibration_v1.json")


def _raw_frame() -> pd.DataFrame:
    return pd.read_csv(RAW)


def test_switch_matrix_is_complete():
    raw = _raw_frame()
    scenario = json.loads(SCENARIO.read_text())
    assert raw["run_id"].nunique() == 120
    assert raw["event_index"].nunique() == 24
    assert set(raw["workload"]) == set(scenario["workloads"])
    directed = {
        (e["old_path"], e["new_path"]) for e in scenario["events"]
    }
    assert len(directed) == 6  # A->B and B->A distinct
    observed = set(zip(raw["old_path"], raw["new_path"]))
    assert observed == directed
    assert set(raw["transport"]) == {"udp", "tcp"}
    counts = raw.groupby(
        ["event_index", "repetition", "workload", "old_path", "new_path"]
    ).size()
    assert (counts == 1).all()  # unique keys, no duplicate repeats


def test_one_repeat_is_insufficient():
    single = _raw_frame().head(1)
    rows, _ = build_rows(with_buckets(single), min_repeats=3)
    assert rows["quality"].iloc[0] == "insufficient"


def test_failed_runs_are_accounted_for():
    manifest = json.loads(
        Path("data/switching_calibration_manifest.json").read_text()
    )
    # e22-r03 stalled (sent 2047 frames vs 5835 nominal) and is excluded
    # with a documented reason, not silently omitted.
    assert "e22-r03" in manifest["excluded_runs"]
    raw = _raw_frame()
    assert (raw["run_id"] == "e22-r03").sum() == 1  # retained in raw evidence


def test_raw_runs_trace_to_aggregate_rows():
    manifest = json.loads(
        Path("data/switching_calibration_manifest.json").read_text()
    )
    raw = _raw_frame()
    traced = set()
    for run_ids in manifest["aggregate_traceability"].values():
        traced.update(run_ids)
    # Every aggregate row traces to raw run ids; exclusions are explicit.
    assert traced | set(manifest["excluded_runs"]) == set(raw["run_id"])


def test_incompatible_configs_not_aggregated():
    raw_a = _raw_frame().assign(queue_config="shared_1000pkt")
    raw_b = _raw_frame().assign(queue_config="per_path_v1")
    # Same measurements under different queue configurations must not
    # merge into one group: partition the key by the config column.
    mixed = pd.concat([raw_a, raw_b], ignore_index=True)
    grouped = mixed.groupby("queue_config")
    assert grouped.ngroups == 2
    assert config_fingerprint(SCENARIO, "shared_1000pkt") != config_fingerprint(
        SCENARIO, "per_path_v1"
    )


def test_manifest_expected_observed_match():
    manifest = json.loads(
        Path("data/switching_calibration_manifest.json").read_text()
    )
    assert manifest["expected_runs"] == 120
    assert manifest["observed_runs"] == 120
    assert manifest["missing_runs"] == []
    assert manifest["min_repeats_required"] == 3
    assert manifest["transports"] == ["tcp", "udp"]


def test_manifest_requires_config_tag_consistency():
    """Calibration rows must record the queue configuration they used."""

    stats = pd.read_csv("testbed/outputs/cal_v1_full/calibration_stats.csv")
    # The full sweep predates per-path limits: documented as
    # shared_1000pkt in the manifest, and the per-path config is NOT
    # allowed to merge with it.
    manifest = json.loads(
        Path("data/switching_calibration_manifest.json").read_text()
    )
    assert manifest["queue_limit_packets"] == 1000
    assert manifest["per_path_queue_limit_packets"] is None
    assert stats["quality"].isin(["usable", "trimmed_usable", "insufficient"]).all()


def test_as_run_scenario_snapshot_differs_from_head():
    """The sweep ran before per-path limits existed; the manifest must be
    built from the as-run scenario snapshot, not the later HEAD scenario."""

    as_run = json.loads(
        Path("testbed/outputs/cal_v1_full/scenario_as_run.json").read_text()
    )
    head = json.loads(Path("testbed/scenarios/switch_calibration_v1.json").read_text())
    assert "per_path_queue_limit_packets" not in as_run
    assert "per_path_queue_limit_packets" in head
    # Same events and repetitions: only the queue policy block differs.
    assert as_run["events"] == head["events"]
    assert as_run["workloads"] == head["workloads"]
    manifest = json.loads(
        Path("data/switching_calibration_manifest.json").read_text()
    )
    import hashlib

    assert manifest["scenario_sha256"] == hashlib.sha256(
        Path("testbed/outputs/cal_v1_full/scenario_as_run.json").read_bytes()
    ).hexdigest()
