"""Plumbing tests for the cross-engine comparator using SYNTHETIC fixtures.

Every fixture in this module is synthetic: case names carry a SYNTHETIC
prefix, values are invented constants, and the thresholds tables are
hand-written. These tests exercise only the comparator plumbing - CSV
loading, key validation, band-column resolution, decide() gating, exit
codes, and the explicit missing-band failure. They construct no matched
emulator/Mininet observations and say nothing about engine agreement.

The band rows used here are synthetic placeholders, NOT proposed or
adopted reproducibility bands.
"""

import csv
import sys
from pathlib import Path

import pytest

from scripts import cross_engine_compare as cec

REPO_ROOT = Path(__file__).resolve().parents[1]

# Synthetic band values; not derived from any measurement.
SYN_BAND = 0.05
SYN_BAND_ALT = 0.20


def _write_long_csv(path: Path, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "metric", "value"])
        writer.writerows(rows)


def _write_thresholds(path: Path, extra_columns: bool = False) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if extra_columns:
            writer.writerow(["metric", "cell_half_range_q90",
                             "max_dev_from_median_q90"])
            writer.writerow(["synthetic_metric", SYN_BAND, SYN_BAND_ALT])
        else:
            writer.writerow(["metric", "cell_half_range_q90"])
            writer.writerow(["synthetic_metric", SYN_BAND])


def _synthetic_rows(values):
    return [("SYNTHETIC_CASE_A", "synthetic_metric", v) for v in values]


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["cross_engine_compare.py", *argv])
    return cec.main()


def test_plumbing_accepts_identical_synthetic_tables(tmp_path, monkeypatch):
    emu = tmp_path / "emu.csv"
    mini = tmp_path / "mini.csv"
    thr = tmp_path / "thr.csv"
    out = tmp_path / "out.csv"
    values = [1.0, 1.1, 0.9, 1.05, 1.0]
    _write_long_csv(emu, _synthetic_rows(values))
    _write_long_csv(mini, _synthetic_rows(values))
    _write_thresholds(thr)

    rc = _run_cli(monkeypatch, [
        "--emulator", str(emu), "--mininet", str(mini),
        "--thresholds", str(thr), "--out", str(out), "--check",
    ])
    assert rc == 0
    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert len(rows) == 1
    assert rows[0]["case"] == "SYNTHETIC_CASE_A"
    assert rows[0]["accepted"] == "True"
    assert float(rows[0]["band"]) == pytest.approx(SYN_BAND)


def test_plumbing_rejects_synthetic_shift_beyond_band(tmp_path, monkeypatch):
    emu = tmp_path / "emu.csv"
    mini = tmp_path / "mini.csv"
    thr = tmp_path / "thr.csv"
    out = tmp_path / "out.csv"
    _write_long_csv(emu, _synthetic_rows([1.0, 1.1, 0.9, 1.05, 1.0]))
    _write_long_csv(mini, _synthetic_rows([2.0, 2.1, 1.9, 2.05, 2.0]))
    _write_thresholds(thr)

    rc = _run_cli(monkeypatch, [
        "--emulator", str(emu), "--mininet", str(mini),
        "--thresholds", str(thr), "--out", str(out), "--check",
    ])
    assert rc == 1
    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert rows[0]["accepted"] == "False"


def test_missing_band_is_explicit_error_not_silent_pass(tmp_path, monkeypatch, capsys):
    """A metric with no derived band (queue_delay_ms stands in here, as it
    has no adopted estimator) must fail loudly with exit 2."""
    emu = tmp_path / "emu.csv"
    mini = tmp_path / "mini.csv"
    thr = tmp_path / "thr.csv"
    out = tmp_path / "out.csv"
    rows = _synthetic_rows([1.0, 1.1]) + [
        ("SYNTHETIC_CASE_A", "queue_delay_ms", 3.0),
        ("SYNTHETIC_CASE_A", "queue_delay_ms", 3.1),
    ]
    _write_long_csv(emu, rows)
    _write_long_csv(mini, rows)
    _write_thresholds(thr)

    rc = _run_cli(monkeypatch, [
        "--emulator", str(emu), "--mininet", str(mini),
        "--thresholds", str(thr), "--out", str(out), "--check",
    ])
    assert rc == 2
    assert "no derived band" in capsys.readouterr().err
    assert not out.exists()


def test_band_column_resolution_prefers_half_range(tmp_path):
    """When both band columns exist, the honest half-range name wins."""
    thr = tmp_path / "thr.csv"
    _write_thresholds(thr, extra_columns=True)
    bands = cec._load_thresholds(thr)
    assert bands["synthetic_metric"] == pytest.approx(SYN_BAND)
    assert bands["synthetic_metric"] != pytest.approx(SYN_BAND_ALT)


def test_key_mismatch_is_explicit_error(tmp_path, monkeypatch, capsys):
    emu = tmp_path / "emu.csv"
    mini = tmp_path / "mini.csv"
    thr = tmp_path / "thr.csv"
    _write_long_csv(emu, _synthetic_rows([1.0, 1.1]))
    _write_long_csv(mini, [("SYNTHETIC_CASE_B", "synthetic_metric", 1.0)])
    _write_thresholds(thr)

    rc = _run_cli(monkeypatch, [
        "--emulator", str(emu), "--mininet", str(mini),
        "--thresholds", str(thr), "--out", str(tmp_path / "out.csv"),
    ])
    assert rc == 2
    assert "exactly the same" in capsys.readouterr().err
