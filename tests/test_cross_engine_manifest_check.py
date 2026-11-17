"""Manifest gap-diagnostic tests. Fixtures only; no scenarios constructed."""

import csv
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cross_engine_manifest_check.py"
COMMITTED_MANIFEST = ROOT / "testbed" / "scenarios" / "cross_engine_cases.json"
COMMITTED_THRESHOLDS = ROOT / "analysis" / "cross_engine_thresholds.csv"
COMMITTED_REFERENCE = ROOT / "testbed" / "scenarios" / "switch_calibration_v2.json"

BAND_COLUMN_CANDIDATES = ("cell_half_range_q90", "max_dev_from_median_q90")


def run_script(cwd, *args):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          env=env, capture_output=True, text=True, timeout=15)


def committed_band_column():
    with open(COMMITTED_THRESHOLDS, newline="", encoding="utf-8") as handle:
        fieldnames = csv.DictReader(handle).fieldnames or []
    return next(c for c in BAND_COLUMN_CANDIDATES if c in fieldnames)


def write_thresholds(path, metrics):
    band = committed_band_column()
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", band])
        for metric in metrics:
            writer.writerow([metric, 0.01])


def test_committed_manifest_reports_current_gaps(tmp_path):
    result = run_script(tmp_path, "--json")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["runner_executable"] is False
    # Currently true gaps, asserted as a subset so the test stays correct
    # when one gap is later fixed.
    missing = set(report["metrics_without_bands"])
    assert {"queue_delay_ms", "throughput_mbps", "delay_median_ms", "jitter_mean_ms"} <= missing
    assert "missing runner section: paths" in report["gaps"]
    assert "missing runner section: workloads" in report["gaps"]
    assert "missing runner section: events" in report["gaps"]
    assert "missing runner section: server_ip" in report["gaps"]
    assert "NOT directly loadable" in report["runner_note"]
    assert report["scientific_validity"] == "not_evaluated"


def test_runner_shaped_scenario_with_band_coverage_exits_zero(tmp_path):
    # A genuinely runner-schema-complete scenario (same shape as
    # testbed/scenarios/smoke.json) with a bands CSV covering its metrics.
    scenario = {
        "name": "synthetic_runner_shaped",
        "server_ip": "10.0.0.100",
        "paths": {
            "bb": {"capacity_mbps": 50.0, "one_way_delay_ms": 20.0,
                   "jitter_ms": 1.0, "loss_pct": 0.0},
            "five_g": {"capacity_mbps": 30.0, "one_way_delay_ms": 30.0,
                       "jitter_ms": 3.0, "loss_pct": 0.2},
        },
        "workloads": {
            "voice": {"flow_type": "voice", "transport": "udp",
                      "client_ip": "10.0.0.11", "server_port": 5004,
                      "rate_mbps": 0.15, "duration_s": 10.0,
                      "warmup_s": 4.0, "packet_bytes": 240},
        },
        "events": [{"workload": "voice", "old_path": "bb", "new_path": "five_g"}],
    }
    manifest = tmp_path / "scenario.json"
    manifest.write_text(json.dumps(scenario))
    thresholds = tmp_path / "bands.csv"
    write_thresholds(thresholds, ["loss_frac"])
    result = run_script(tmp_path, "--manifest", str(manifest),
                        "--thresholds", str(thresholds), "--json")
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["runner_executable"] is True
    assert report["gaps"] == []


def test_unreadable_manifest_exits_two(tmp_path):
    result = run_script(tmp_path, "--manifest", str(tmp_path / "missing.json"))
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_thresholds_without_band_column_exits_two(tmp_path):
    bad = tmp_path / "bad_thresholds.csv"
    bad.write_text("metric,some_other_column\nloss_frac,0.01\n")
    result = run_script(tmp_path, "--thresholds", str(bad))
    assert result.returncode == 2
    assert "no band column" in result.stderr
    assert "cell_half_range_q90" in result.stderr
    assert "max_dev_from_median_q90" in result.stderr


def test_repository_anchored_defaults_from_foreign_cwd(tmp_path):
    # cwd outside the repo: defaults must resolve against the repo root.
    result = run_script(tmp_path, "--json")
    assert result.returncode in (0, 1), result.stderr
    report = json.loads(result.stdout)
    assert report["manifest"] == str(COMMITTED_MANIFEST)
    assert report["thresholds"] == str(COMMITTED_THRESHOLDS)
    assert report["reference"] == str(COMMITTED_REFERENCE)
