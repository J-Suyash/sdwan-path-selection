"""Offline RL export gate tests (spec section 6)."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_datasets import validation_is_accepted, ACCEPTANCE_PATH


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


def test_validation_gate_accepts_documented_run(tmp_path, monkeypatch):
    target = tmp_path / "acceptance.json"
    target.write_text(
        json.dumps({"accepted": True, "validation_run_id": "cal_v1_full"})
    )
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    assert validation_is_accepted(str(target)) is True


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
