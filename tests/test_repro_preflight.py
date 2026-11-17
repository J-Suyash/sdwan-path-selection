"""File-presence checks deliberately use fake bytes, not parquet validation."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repro_preflight.py"
spec = importlib.util.spec_from_file_location("repro_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def populate(root):
    root.mkdir(exist_ok=True)
    for stem in preflight.SOURCE_FILES.values():
        (root / (stem + ".parquet")).write_bytes(b"not-parquet: presence only\n")


def test_complete_files_are_not_scientific_validation(tmp_path, capsys):
    populate(tmp_path)
    result = preflight.main(["--data-root", str(tmp_path), "--json", "--hash"])
    report = json.loads(capsys.readouterr().out)
    assert result == (0 if sys.version_info[:2] == (3, 11) else 1)
    assert report["overall_ok"] == (sys.version_info[:2] == (3, 11))
    assert report["scientific_validity"] == "not_evaluated"
    assert report["check_mode"] == "file_presence_only"
    expected = hashlib.sha256(b"not-parquet: presence only\n").hexdigest()
    assert all(item["sha256"] == expected for item in report["files"].values())


@pytest.mark.parametrize("kind", ["missing", "empty", "directory"])
def test_unusable_input_exits_nonzero(tmp_path, capsys, kind):
    populate(tmp_path)
    target = tmp_path / "collected.parquet"
    target.unlink()
    if kind == "empty":
        target.touch()
    elif kind == "directory":
        target.mkdir()
    assert preflight.main(["--data-root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["overall_ok"] is False
    assert report["files"]["bb"]["exists"] == (kind != "missing")


def test_hash_read_error_never_reports_success(tmp_path, monkeypatch, capsys):
    populate(tmp_path)
    def denied(path):
        raise PermissionError("test read failure")
    monkeypatch.setattr(preflight, "_sha256_file", denied)
    assert preflight.main(["--data-root", str(tmp_path), "--json", "--hash"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["overall_ok"] is False
    assert report["files"]["bb"]["error"]["type"] == "PermissionError"


def test_wrong_python_is_explicit_failure(tmp_path, monkeypatch, capsys):
    populate(tmp_path)
    monkeypatch.setattr(preflight.sys, "version_info", (3, 12, 0))
    assert preflight.main(["--data-root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["python_version_ok"] is False
    assert report["overall_ok"] is False


def run_from(cwd, *args):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          env=env, capture_output=True, text=True, timeout=15)


def test_default_root_is_repository_anchored(tmp_path):
    result = run_from(tmp_path, "--json")
    report = json.loads(result.stdout)
    assert Path(report["data_root"]) == ROOT / "data" / "processed"
    assert result.returncode in (0, 1)
    assert result.stderr == ""


def test_explicit_relative_root_is_cwd_relative(tmp_path):
    populate(tmp_path / "inputs")
    result = run_from(tmp_path, "--data-root", "inputs", "--json")
    report = json.loads(result.stdout)
    assert all(item["exists"] for item in report["files"].values())
    assert result.returncode == (0 if sys.version_info[:2] == (3, 11) else 1)


def test_help_and_bad_arguments(tmp_path):
    result = run_from(tmp_path, "--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout
    result = run_from(tmp_path, "--unknown-flag")
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
