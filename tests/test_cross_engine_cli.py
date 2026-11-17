"""Comparator CLI plumbing fixtures. No measurements or acceptance created."""

import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cross_engine_compare.py"


def values(value=0.01, case="caseA", metric="loss_frac"):
    return pd.DataFrame([{"case": case, "metric": metric, "value": value} for _ in range(5)])


def invoke(tmp_path, emulator=None, mininet=None, bands=None, check=False):
    (values() if emulator is None else emulator).to_csv(tmp_path / "emulator.csv", index=False)
    (values() if mininet is None else mininet).to_csv(tmp_path / "mininet.csv", index=False)
    if bands is None:
        bands = pd.DataFrame([{"metric": "loss_frac", "max_dev_from_median_q90": 0.01}])
    bands.to_csv(tmp_path / "bands.csv", index=False)
    out = tmp_path / "out.csv"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, str(SCRIPT), "--emulator", str(tmp_path / "emulator.csv"),
           "--mininet", str(tmp_path / "mininet.csv"), "--thresholds", str(tmp_path / "bands.csv"), "--out", str(out)]
    if check:
        cmd.append("--check")
    result = subprocess.run(cmd, cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
    return result, out


@pytest.mark.parametrize("check", [False, True])
def test_matching_fixture_passes(tmp_path, check):
    result, out = invoke(tmp_path, check=check)
    assert result.returncode == 0, result.stderr
    frame = pd.read_csv(out)
    assert len(frame) == 1 and frame.accepted.all()
    assert {"median_diff", "ks_statistic", "cliffs_delta", "tail_ratio_p95", "accepted"} <= set(frame)


@pytest.mark.parametrize("check,expected", [(False, 0), (True, 1)])
def test_rejection_report_versus_check(tmp_path, check, expected):
    result, out = invoke(tmp_path, emulator=values(.8), check=check)
    assert result.returncode == expected, result.stderr
    assert not pd.read_csv(out).accepted.any()
    assert "REPORT" in result.stdout.upper() if not check else "CHECK" in result.stdout.upper()


@pytest.mark.parametrize("side", ["emulator", "mininet"])
def test_unpaired_group_is_input_error(tmp_path, side):
    frame = pd.concat([values(), values(case="caseB")], ignore_index=True)
    result, out = invoke(tmp_path, **{side: frame})
    assert result.returncode == 2
    assert not out.exists()
    assert "Traceback" not in result.stderr
    assert "caseB" in result.stderr


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "invalid"])
def test_bad_values_rejected(tmp_path, bad):
    frame = values().astype({"value": object});frame.loc[0, "value"] = bad
    result, out = invoke(tmp_path, emulator=frame)
    assert result.returncode == 2 and not out.exists()
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("column", ["case", "metric", "value"])
def test_missing_columns_rejected(tmp_path, column):
    result, out = invoke(tmp_path, emulator=values().drop(columns=[column]))
    assert result.returncode == 2 and not out.exists()
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("column", ["case", "metric"])
def test_empty_identifier_rejected(tmp_path, column):
    frame = values();frame.loc[0, column] = " "
    result, out = invoke(tmp_path, mininet=frame)
    assert result.returncode == 2 and not out.exists()


def test_empty_table_rejected(tmp_path):
    result, out = invoke(tmp_path, emulator=values().iloc[:0])
    assert result.returncode == 2 and not out.exists()


@pytest.mark.parametrize("bad", [-1., float("nan"), float("inf"), "invalid"])
def test_bad_threshold_rejected(tmp_path, bad):
    bands = pd.DataFrame([{"metric": "loss_frac", "max_dev_from_median_q90": bad}])
    result, out = invoke(tmp_path, bands=bands)
    assert result.returncode == 2 and not out.exists()
    assert "Traceback" not in result.stderr


def test_duplicate_threshold_rejected(tmp_path):
    bands = pd.DataFrame([{"metric": "loss_frac", "max_dev_from_median_q90": .01}] * 2)
    result, out = invoke(tmp_path, bands=bands)
    assert result.returncode == 2 and not out.exists()


def test_unknown_metric_rejected_without_partial_output(tmp_path):
    frame = pd.concat([values(), values(metric="queue_delay_ms")], ignore_index=True)
    result, out = invoke(tmp_path, emulator=frame, mininet=frame)
    assert result.returncode == 2 and not out.exists()
    assert "queue_delay_ms" in result.stderr


def test_input_error_preserves_existing_report(tmp_path):
    out = tmp_path / "out.csv";out.write_text("existing-report\n")
    result, out = invoke(tmp_path, mininet=values(case="different"))
    assert result.returncode == 2
    assert out.read_text() == "existing-report\n"


def test_missing_file_has_no_traceback(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--emulator", str(tmp_path / "missing.csv"),
                             "--mininet", str(tmp_path / "also-missing.csv")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("column", ["metric", "max_dev_from_median_q90"])
def test_threshold_columns_required(tmp_path, column):
    bands = pd.DataFrame([{"metric": "loss_frac", "max_dev_from_median_q90": .01}]).drop(columns=[column])
    result, out = invoke(tmp_path, bands=bands)
    assert result.returncode == 2 and not out.exists()
    assert "Traceback" not in result.stderr


def test_output_io_failure_has_no_traceback(tmp_path):
    (tmp_path / "out.csv").mkdir()
    result, out = invoke(tmp_path)
    assert result.returncode == 2 and out.is_dir()
    assert "Traceback" not in result.stderr


def test_one_case_is_not_implicitly_full_round_acceptance(tmp_path):
    result, out = invoke(tmp_path, check=True)
    assert result.returncode == 0 and out.exists()
    assert "not whole-round scientific acceptance" in result.stdout


def test_help_explains_compatibility(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    assert "--check" in result.stdout
    assert "report only" in result.stdout
