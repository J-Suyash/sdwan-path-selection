"""Offline RL export gate tests (spec section 6)."""

import hashlib
import json
import shutil
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


def _bind_revision(monkeypatch, head="f" * 40, clean=True):
    """Mock the revision-binding helpers for gate-level tests."""

    monkeypatch.setattr(
        "scripts.generate_datasets._current_head_revision",
        lambda repo_root: head,
    )
    monkeypatch.setattr(
        "scripts.generate_datasets._resolve_recorded_revision",
        lambda repo_root, recorded: (
            head if recorded == FULL_ACCEPTANCE["code_revision"] else None
        ),
    )
    monkeypatch.setattr(
        "scripts.generate_datasets._tracked_tree_is_clean",
        lambda repo_root: clean,
    )


def _accepted_payload_file(tmp_path, **overrides):
    payload = dict(FULL_ACCEPTANCE)
    payload.update(overrides)
    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps(payload))
    return str(target)


def test_validation_gate_accepts_reviewed_provenanced_run(tmp_path, monkeypatch):
    target = tmp_path / "acceptance.json"
    target.write_text(json.dumps(FULL_ACCEPTANCE))
    monkeypatch.setattr(
        "scripts.generate_datasets.ACCEPTANCE_PATH", str(target)
    )
    _bind_revision(monkeypatch)
    assert validation_is_accepted(str(target)) is True


def test_validation_gate_rejects_stale_revision(tmp_path, monkeypatch):
    """A recorded revision that resolves, but to a different commit than
    HEAD, fails: any post-validation commit invalidates the artefact."""

    _bind_revision(monkeypatch)
    monkeypatch.setattr(
        "scripts.generate_datasets._resolve_recorded_revision",
        lambda repo_root, recorded: "a" * 40,
    )
    assert validation_is_accepted(_accepted_payload_file(tmp_path)) is False


def test_recorded_revision_rejects_non_hex_object_names(tmp_path):
    """Symbolic refs, revspecs, option-like and short strings never reach git."""

    from scripts.generate_datasets import _resolve_recorded_revision

    for bogus in ("HEAD", "main", "v1.0", "2e2e2cd^{commit}", "2e2e2~1",
                  "--all", "", "ab", "not-a-commit", "2e2e2cd "):
        assert _resolve_recorded_revision(tmp_path, bogus) is None, bogus


def test_validation_gate_fails_closed_without_git(tmp_path, monkeypatch):
    """Unresolvable HEAD (git unavailable) rejects a complete payload."""

    _bind_revision(monkeypatch, head=None)
    assert validation_is_accepted(_accepted_payload_file(tmp_path)) is False


def test_validation_gate_rejects_dirty_tracked_tree(tmp_path, monkeypatch):
    """Uncommitted tracked changes are not bound by HEAD equality."""

    _bind_revision(monkeypatch, clean=False)
    assert validation_is_accepted(_accepted_payload_file(tmp_path)) is False


GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git not available")


def _init_repo(path: Path) -> str:
    subprocess.run([GIT, "init", "-q", str(path)], check=True)
    subprocess.run([GIT, "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run([GIT, "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "tracked.txt").write_text("one\n")
    subprocess.run([GIT, "-C", str(path), "add", "tracked.txt"], check=True)
    subprocess.run([GIT, "-C", str(path), "commit", "-q", "-m", "init"], check=True)
    return subprocess.run(
        [GIT, "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@requires_git
def test_revision_binding_against_real_repository(tmp_path, monkeypatch):
    from scripts import generate_datasets as gd

    repo = tmp_path / "repo"
    repo.mkdir()
    head = _init_repo(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # explicit repo root: cwd must not matter
    assert gd._current_head_revision(repo) == head
    assert gd._resolve_recorded_revision(repo, head) == head
    assert gd._resolve_recorded_revision(repo, head[:7]) == head  # abbreviation
    assert gd._tracked_tree_is_clean(repo) is True
    # Untracked files (the artefact lives in one) do not dirty the tree.
    (repo / "data").mkdir()
    (repo / "data" / "acceptance.json").write_text("{}")
    assert gd._tracked_tree_is_clean(repo) is True
    # Symbolic refs never resolve as recorded evidence.
    assert gd._resolve_recorded_revision(repo, "HEAD") is None
    # An all-hex tag pointing at HEAD cannot impersonate a hash prefix.
    subprocess.run([GIT, "-C", str(repo), "tag", "deadbee"], check=True)
    assert gd._resolve_recorded_revision(repo, "deadbee") is None
    # A tracked modification fails the cleanliness check.
    (repo / "tracked.txt").write_text("two\n")
    assert gd._tracked_tree_is_clean(repo) is False


@requires_git
def test_recorded_revision_binds_immutably_across_commits(tmp_path):
    """The recorded hex id keeps resolving to the OLD commit after any new
    commit (docs-only included), so binding fails until re-validation."""

    from scripts import generate_datasets as gd

    repo = tmp_path / "repo"
    repo.mkdir()
    head = _init_repo(repo)
    (repo / "tracked.txt").write_text("two\n")
    subprocess.run([GIT, "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run([GIT, "-C", str(repo), "commit", "-q", "-m", "docs only"], check=True)
    new_head = gd._current_head_revision(repo)
    assert new_head is not None and new_head != head
    assert gd._resolve_recorded_revision(repo, head[:7]) == head


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
