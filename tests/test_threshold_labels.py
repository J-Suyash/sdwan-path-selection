"""Band-column naming: honest cell_half_range_q90 accepted, legacy name kept.

Fixtures only; no measurements or acceptance artefacts are created.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMPARE = ROOT / "scripts" / "cross_engine_compare.py"
DERIVE = ROOT / "scripts" / "derive_cross_engine_thresholds.py"
COMMITTED_CSV = ROOT / "analysis" / "cross_engine_thresholds.csv"
REPEATABILITY = [
    ROOT / "testbed" / "outputs" / "cal_v1_full" / "repeatability.json",
    ROOT / "testbed" / "outputs" / "cal_v2_perpath" / "repeatability.json",
]


def values(value=0.01, case="caseA", metric="loss_frac"):
    return pd.DataFrame([{"case": case, "metric": metric, "value": value} for _ in range(5)])


def invoke_compare(tmp_path, bands, emulator=None, check=False):
    (values() if emulator is None else emulator).to_csv(tmp_path / "emulator.csv", index=False)
    values().to_csv(tmp_path / "mininet.csv", index=False)
    bands.to_csv(tmp_path / "bands.csv", index=False)
    out = tmp_path / "out.csv"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, str(COMPARE), "--emulator", str(tmp_path / "emulator.csv"),
           "--mininet", str(tmp_path / "mininet.csv"), "--thresholds", str(tmp_path / "bands.csv"),
           "--out", str(out)]
    if check:
        cmd.append("--check")
    result = subprocess.run(cmd, cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
    return result, out


def invoke_derive(tmp_path, repeatability_paths):
    out = tmp_path / "derived.csv"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, str(DERIVE), "--out", str(out)]
    for path in repeatability_paths:
        cmd += ["--repeatability", str(path)]
    result = subprocess.run(cmd, cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)
    return result, out


def test_new_band_column_accepted(tmp_path):
    bands = pd.DataFrame([{"metric": "loss_frac", "cell_half_range_q90": 0.01}])
    result, out = invoke_compare(tmp_path, bands)
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(out).accepted.all()


def test_legacy_band_column_still_accepted(tmp_path):
    bands = pd.DataFrame([{"metric": "loss_frac", "max_dev_from_median_q90": 0.01}])
    result, out = invoke_compare(tmp_path, bands)
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(out).accepted.all()


def test_new_column_wins_when_both_present(tmp_path):
    # Legacy column generous, honest column strict: --check must fail,
    # proving cell_half_range_q90 drove the decision.
    bands = pd.DataFrame([{
        "metric": "loss_frac",
        "cell_half_range_q90": 0.001,
        "max_dev_from_median_q90": 100.0,
    }])
    result, out = invoke_compare(tmp_path, bands, emulator=values(0.5), check=True)
    assert result.returncode == 1, result.stderr
    assert not pd.read_csv(out).accepted.any()


def test_missing_band_column_is_clear_input_error(tmp_path):
    bands = pd.DataFrame([{"metric": "loss_frac", "some_other_column": 0.01}])
    result, out = invoke_compare(tmp_path, bands)
    assert result.returncode == 2
    assert not out.exists()
    assert "Traceback" not in result.stderr
    assert "cell_half_range_q90" in result.stderr
    assert "max_dev_from_median_q90" in result.stderr


def test_derive_emits_honest_columns_and_unchanged_numbers(tmp_path):
    rows = [{
        "flow_type": "voice", "transport": "udp",
        "old_rtt_ms": 40.0, "new_rtt_ms": 60.0,
        "old_jitter_ms": 0.3, "new_jitter_ms": 1.0,
        "in_flight_bucket": "medium", "occupancy_bucket": "low",
        "quality": "usable", "n_runs": 5,
        "interruption_s_mean": 0.005, "interruption_s_min": 0.0, "interruption_s_max": 0.01,
        "loss_frac_mean": 0.01, "loss_frac_min": 0.0, "loss_frac_max": 0.02,
        "reordering_frac_mean": 0.0, "reordering_frac_min": 0.0, "reordering_frac_max": 0.0,
    }]
    fixture = tmp_path / "repeatability.json"
    fixture.write_text(json.dumps(rows))
    result, out = invoke_derive(tmp_path, [fixture])
    assert result.returncode == 0, result.stderr
    frame = pd.read_csv(out)
    assert {"cell_half_range_median", "cell_half_range_q90", "cell_half_range_q95"} <= set(frame.columns)
    assert "max_dev_from_median_q90" not in frame.columns
    row = frame.set_index("metric").loc["loss_frac"]
    assert row["cell_half_range_median"] == 0.01  # (0.02 - 0) / 2, unchanged formula
    # Skew fixture: min 0 / max 10 yields half-range 5.0, NOT max deviation
    # from the median (10). The honest column name says what it is.
    rows[0]["loss_frac_max"] = 10.0
    fixture.write_text(json.dumps(rows))
    result, out = invoke_derive(tmp_path, [fixture])
    assert result.returncode == 0, result.stderr
    skewed = pd.read_csv(out).set_index("metric").loc["loss_frac"]
    assert skewed["cell_half_range_median"] == 5.0


def test_derive_reproduces_committed_bands_exactly(tmp_path):
    """Only names changed: re-deriving from both committed repeatability
    files must reproduce the committed band values bit-for-bit."""

    result, out = invoke_derive(tmp_path, REPEATABILITY)
    assert result.returncode == 0, result.stderr
    derived = pd.read_csv(out).set_index("metric")
    committed = pd.read_csv(COMMITTED_CSV).set_index("metric")
    for metric in ("interruption_s", "loss_frac", "reordering_frac"):
        assert derived.loc[metric, "cell_half_range_q90"] == \
            committed.loc[metric, "max_dev_from_median_q90"], metric
