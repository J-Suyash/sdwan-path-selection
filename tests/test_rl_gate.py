"""Offline RL export gate tests (spec section 6)."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_datasets import (
    validation_is_accepted,
    ACCEPTANCE_PATH,
    REQUIRED_ACCEPTANCE_FIELDS,
)
from scripts.verify_episode_groups import check_disjointness


def test_validation_gate_rejects_missing_acceptance(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH",
        str(tmp_path / "acceptance.json"),
    )
    assert validation_is_accepted(str(tmp_path / "acceptance.json")) is False


def test_validation_gate_rejects_unaccepted_payload(tmp_path, monkeypatch):
    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps({"accepted": False, "validation_run_id": "x"}))
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    assert validation_is_accepted(str(target)) is False


def test_validation_gate_rejects_bare_acceptance(tmp_path, monkeypatch):
    """A bare accepted:true is not sufficient — provenance fields required."""

    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps({"accepted": True, "validation_run_id": "r1"}))
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    assert validation_is_accepted(str(target)) is False


FULL_ACCEPTANCE = {
    "accepted": True,
    "validation_run_id": "cal_v2_perpath_ce_1",
    "code_revision": "2e2e2cd",
    "config_fingerprints": ["<fingerprint>|per_path_v2"],
    "trace_set_sha256": ["<sha>"],
    "reviewed_by": ["owner"],
    "validation_cases": ["ce01_queue_saturation", "ce02_sla_boundary"],
}


def test_validation_gate_accepts_reviewed_provenanced_run(tmp_path, monkeypatch):
    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps(FULL_ACCEPTANCE))
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    assert validation_is_accepted(str(target)) is True


@pytest.mark.parametrize(
    "missing_field",
    ["code_revision", "config_fingerprints", "trace_set_sha256", "reviewed_by"],
)
def test_validation_gate_requires_each_provenance_field(
    tmp_path, monkeypatch, missing_field
):
    payload = {k: v for k, v in FULL_ACCEPTANCE.items() if k != missing_field}
    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps(payload))
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    assert validation_is_accepted(str(target)) is False


def test_finalize_refused_without_acceptance(tmp_path, monkeypatch):
    """Final export without an accepted validation run must fail loudly."""

    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_datasets.py",
            "--finalize",
            "--datasets",
            "d1",
            "--hours",
            "1",
            "--out",
            str(tmp_path / "final"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "cross-engine validation" in result.stderr
    assert not (tmp_path / "final" / "manifest.csv").exists()


def test_episode_splits_group_by_seed_and_scenario(tmp_path, monkeypatch):
    """Generated episode rows carry a leakage-safe split_group key."""

    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    out = tmp_path / "preliminary"
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_datasets.py",
            "--datasets",
            "d1",
            "--hours",
            "2",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    manifest = pd.read_csv(out / "manifest.csv")
    assert "split_group" in manifest.columns
    groups = manifest["split_group"].unique()
    assert len(groups) == len(manifest)  # distinct seeds -> distinct groups
    payload = json.loads(groups[0])
    assert {"profile", "regime", "seed", "trace_window_start"} <= set(payload)


def test_episode_group_disjointness_enforced():
    manifest = pd.DataFrame(
        {"split_group": ['{"profile": "m", "seed": 0}',
                         '{"profile": "m", "seed": 1}',
                         '{"profile": "m", "seed": 2}']}
    )
    groups = manifest["split_group"].tolist()
    assignment = {
        groups[0]: "train",
        groups[1]: "validation",
        groups[2]: "test",
    }
    report = check_disjointness(manifest, assignment)
    assert report["overlaps"] == []
    assert report["distinct_groups"] == 3


def test_episode_group_overlap_rejected():
    """A group mapped via both key forms to different partitions is a
    conflict and must be rejected, never silently resolved."""

    manifest = pd.DataFrame({"split_group": ["g0", "g1"]})
    conflicting = {
        "g0": "train",
        hashlib.sha256(b"g0").hexdigest(): "test",  # same group, other split
        "g1": "validation",
    }
    with pytest.raises(ValueError, match="conflicting partition"):
        check_disjointness(manifest, conflicting)


def test_episode_group_missing_assignment_rejected():
    manifest = pd.DataFrame({"split_group": ["g0", "unknown_group"]})
    with pytest.raises(ValueError, match="no partition assignment"):
        check_disjointness(manifest, {"g0": "train"})
