"""Tests for the matched-run harness SKELETON (scripts/run_emulator_matched_case.py).

Every run here uses tiny synthetic constant conditions inside pytest
fixtures to verify plumbing only: action encoding, constant-series and
fixed-load injection, queue accounting, fail-closed coverage, and event
handling. No validation data is produced.
"""

import csv
import json
from pathlib import Path

import pytest

from env.config import SDWanConfig
from env.sdwan_env import SDWanEnv
from scripts.run_emulator_matched_case import (
    UNSUPPORTED_REASONS,
    encode_action,
    matched_config,
    run_case,
)

PATHS = ("bb", "five_g", "leo")


def _write_scenario(
    tmp_path,
    *,
    rate_mbps=10.0,
    capacity_mbps=100.0,
    events=None,
    duration_s=4.0,
    warmup_s=1.0,
    name="unit_case",
):
    paths = {
        p: {
            "capacity_mbps": capacity_mbps,
            "one_way_delay_ms": 10.0,
            "jitter_ms": 0.0,
            "loss_pct": 0.0,
        }
        for p in PATHS
    }
    doc = {
        "name": name,
        "server_ip": "10.0.0.100",
        "paths": paths,
        "workloads": {
            "w": {
                "flow_type": "bulk",
                "transport": "udp",
                "client_ip": "10.0.0.14",
                "server_port": 9999,
                "rate_mbps": rate_mbps,
                "duration_s": duration_s,
                "warmup_s": warmup_s,
                "packet_bytes": 1400,
            }
        },
        "events": events or [],
        "repetitions": 2,
        "queue_limit_packets": 1000,
    }
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _constant_spec(rtt=20.0, capacity=100.0):
    return {p: {"rtt_ms": rtt, "loss": 0.0, "capacity_mbps": capacity} for p in PATHS}


def _read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_encode_action_roundtrip():
    cfg = SDWanConfig()
    env = SDWanEnv(cfg, seed=1)
    env.reset(seed=1)
    for target in cfg.underlays:
        assignment = {cls: target for cls in cfg.classes}
        assert env._decode(encode_action(assignment, cfg)) == assignment


def test_constant_series_provenance_and_no_synthetic_fallback():
    cfg = SDWanConfig(
        constant_series=_constant_spec(rtt=42.0),
        allow_synthetic_traces=False,
        data_root="/nonexistent",
        episode_seconds=4,
    )
    env = SDWanEnv(cfg, seed=0)
    _, info = env.reset(seed=0)
    for underlay in PATHS:
        series = env.series[underlay]
        assert (series["rtt_ms"] == 42.0).all()
        assert (series["capacity"] == 100.0).all()
        assert info["trace_provenance"][underlay] == "constant-matched"


def test_constant_series_missing_underlay_rejected():
    with pytest.raises(ValueError, match="constant_series missing"):
        SDWanConfig(constant_series={"bb": {"rtt_ms": 1.0, "loss": 0.0, "capacity_mbps": 1.0}})


def test_fixed_load_pinned_across_steps():
    fixed = {"voice": 0.0, "video": 0.0, "interactive": 0.0, "bulk": 5.0}
    cfg = SDWanConfig(
        constant_series=_constant_spec(),
        fixed_load_mbps=fixed,
        episode_seconds=3,
    )
    env = SDWanEnv(cfg, seed=0)
    env.reset(seed=0)
    assert env.load == fixed
    action = encode_action({cls: "bb" for cls in cfg.classes}, cfg)
    env.step(action)
    assert env.load == fixed


def test_fixed_load_missing_class_rejected():
    with pytest.raises(ValueError, match="fixed_load_mbps missing"):
        SDWanConfig(fixed_load_mbps={"bulk": 1.0})


def test_run_case_below_capacity_zero_loss(tmp_path):
    scenario = _write_scenario(tmp_path, rate_mbps=10.0, capacity_mbps=100.0)
    out = tmp_path / "out"
    code = run_case(
        scenario, out_dir=out, required_metrics=["loss_frac", "throughput_mbps"]
    )
    assert code == 0
    rows = _read_csv(out / "emulator_metrics.csv")
    assert len(rows) == 4  # 2 reps x 2 metrics
    for row in rows:
        if row["metric"] == "loss_frac":
            assert float(row["value"]) == 0.0
        else:
            assert float(row["value"]) == pytest.approx(10.0)


def test_run_case_saturation_drops_post_warmup(tmp_path):
    scenario = _write_scenario(tmp_path, rate_mbps=200.0, capacity_mbps=100.0)
    out = tmp_path / "out"
    code = run_case(scenario, out_dir=out, required_metrics=["loss_frac"])
    assert code == 0
    rows = _read_csv(out / "emulator_metrics.csv")
    for row in rows:
        assert 0.45 < float(row["value"]) < 0.55


def test_run_case_fail_closed_on_unsupported_metric(tmp_path):
    scenario = _write_scenario(tmp_path)
    out = tmp_path / "out"
    code = run_case(
        scenario, out_dir=out, required_metrics=["loss_frac", "queue_delay_ms"]
    )
    assert code == 2
    rows = _read_csv(out / "emulator_metrics.csv")
    assert {row["metric"] for row in rows} == {"loss_frac"}
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    entry = coverage["required_metrics"]["queue_delay_ms"]
    assert entry["status"] == "unsupported"
    assert "UNVALIDATED" in entry["reason"]
    assert coverage["fail_closed"] is True
    for metric, reason in UNSUPPORTED_REASONS.items():
        assert reason  # reasons are never blank


def test_run_case_unknown_metric_errors(tmp_path):
    scenario = _write_scenario(tmp_path)
    code = run_case(scenario, out_dir=tmp_path / "out", required_metrics=["bogus"])
    assert code == 1


def test_switch_event_requires_calibration(tmp_path):
    scenario = _write_scenario(
        tmp_path,
        events=[{"workload": "w", "old_path": "five_g", "new_path": "leo"}],
    )
    code = run_case(
        scenario, out_dir=tmp_path / "out", required_metrics=["loss_frac"]
    )
    assert code == 1


def test_switch_event_records_informative_interruption(tmp_path):
    scenario = _write_scenario(
        tmp_path,
        events=[{"workload": "w", "old_path": "five_g", "new_path": "leo"}],
    )
    calibration = tmp_path / "cal.csv"
    calibration.write_text(
        "old_rtt_ms,new_rtt_ms,old_jitter_ms,new_jitter_ms,"
        "packets_in_flight,flow_type,transport,queue_occupancy_frac,"
        "interruption_s,loss_frac,reordering_frac\n"
        "40,60,0,0,100,bulk,tcp,0.5,0.012,0.003,0.001\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    code = run_case(
        scenario,
        calibration_path=str(calibration),
        out_dir=out,
        required_metrics=["loss_frac", "interruption_s"],
    )
    assert code == 0
    rows = _read_csv(out / "emulator_metrics.csv")
    interruption = [r for r in rows if r["metric"] == "interruption_s"]
    assert len(interruption) == 2
    for row in interruption:
        assert float(row["value"]) == pytest.approx(0.012)
        assert row["quality"] == "informative_expected_mismatch"


def test_capacity_event_sag_causes_post_warmup_loss(tmp_path):
    scenario = _write_scenario(
        tmp_path,
        rate_mbps=80.0,
        capacity_mbps=100.0,
        events=[{"workload": "w", "path": "bb", "capacity_mbps": 30.0}],
    )
    out = tmp_path / "out"
    code = run_case(scenario, out_dir=out, required_metrics=["loss_frac"])
    assert code == 0
    rows = _read_csv(out / "emulator_metrics.csv")
    for row in rows:
        assert float(row["value"]) > 0.5  # 80 offered vs 30 sagged capacity
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "raw_unvalidated_scaffolding"
    assert manifest["start_path"] == "bb"


def test_matched_config_uses_case_values(tmp_path):
    scenario_path = _write_scenario(tmp_path, capacity_mbps=150.0)
    from testbed.scenario import load_scenario

    scenario = load_scenario(scenario_path)
    cfg = matched_config(scenario, "w", None)
    assert cfg.cap_mbps["five_g"] == 150.0
    assert cfg.queue_buffer_bytes["bb"] == 1000 * 1400
    assert cfg.allow_synthetic_traces is False
    assert cfg.fixed_load_mbps["bulk"] == 10.0
    assert cfg.fixed_load_mbps["voice"] == 0.0
