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


def test_run_case_saturation_drops_full_run(tmp_path):
    scenario = _write_scenario(tmp_path, rate_mbps=200.0, capacity_mbps=100.0)
    out = tmp_path / "out"
    code = run_case(scenario, out_dir=out, required_metrics=["loss_frac"])
    assert code == 0
    rows = _read_csv(out / "emulator_metrics.csv")
    # Full-run window: step 0 drops 11.1e6 B, steps 1-3 drop 12.5e6 B
    # each (buffer drains and re-admits); 48.6e6 / 100e6 = 0.486.
    for row in rows:
        assert float(row["value"]) == pytest.approx(0.486)


def test_run_case_fail_closed_on_unsupported_metric(tmp_path):
    scenario = _write_scenario(tmp_path)
    out = tmp_path / "out"
    code = run_case(
        scenario, out_dir=out, required_metrics=["loss_frac", "queue_delay_ms"]
    )
    assert code == 2
    # Fail closed end to end: no complete-named CSV may exist.
    assert not (out / "emulator_metrics.csv").exists()
    rows = _read_csv(out / "emulator_metrics.partial.csv")
    assert {row["metric"] for row in rows} == {"loss_frac"}
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    entry = coverage["required_metrics"]["queue_delay_ms"]
    assert entry["status"] == "unsupported"
    assert "UNVALIDATED" in entry["reason"]
    assert coverage["fail_closed"] is True
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["numeric_csv"] == "emulator_metrics.partial.csv"
    for metric, reason in UNSUPPORTED_REASONS.items():
        assert reason  # reasons are never blank


def test_comparator_refuses_incomplete_coverage(tmp_path):
    from scripts.cross_engine_compare import InputError, _load_table

    table = tmp_path / "emulator_metrics.csv"
    table.write_text("case,metric,value\nc1,loss_frac,0.01\n", encoding="utf-8")
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "required_metrics": {
                    "loss_frac": {"status": "expressible"},
                    "queue_delay_ms": {"status": "unsupported", "reason": "x"},
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="coverage incomplete"):
        _load_table(table, "emulator")
    # Complete coverage loads fine.
    (tmp_path / "coverage.json").write_text(
        json.dumps({"required_metrics": {"loss_frac": {"status": "expressible"}}}),
        encoding="utf-8",
    )
    loaded = _load_table(table, "emulator")
    assert len(loaded) == 1


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
    # interruption_s is informative only: never in the comparator CSV.
    assert {row["metric"] for row in rows} == {"loss_frac"}
    informative = _read_csv(out / "emulator_informative.csv")
    interruption = [r for r in informative if r["metric"] == "interruption_s"]
    assert len(interruption) == 2
    for row in interruption:
        assert float(row["value"]) == pytest.approx(0.012)
        assert row["quality"] == "informative_expected_mismatch"
        assert row["calibrated"] == "True"


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
    # Full-run fluid accounting: step 0 clean; step 1 drops 4.85e6 B;
    # steps 2-3 drop 6.25e6 B each (the 1.4e6 B buffer drains and
    # re-admits every step); 17.35e6 / 40e6 = 0.43375.
    for row in rows:
        assert float(row["value"]) == pytest.approx(0.43375)
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


def test_estimator_candidate_rows_emitted_but_never_gate(tmp_path):
    scenario = _write_scenario(tmp_path, rate_mbps=10.0, capacity_mbps=100.0)
    out = tmp_path / "out"
    code = run_case(
        scenario,
        out_dir=out,
        required_metrics=["loss_frac", "delay_median_ms", "jitter_mean_ms"],
    )
    # Coverage gate unchanged: delay/jitter stay unsupported, exit 2.
    assert code == 2
    assert not (out / "emulator_metrics.csv").exists()
    partial = _read_csv(out / "emulator_metrics.partial.csv")
    assert {row["metric"] for row in partial} == {"loss_frac"}
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["required_metrics"]["delay_median_ms"]["status"] == "unsupported"
    assert coverage["required_metrics"]["jitter_mean_ms"]["status"] == "unsupported"
    rows = _read_csv(out / "emulator_estimator.csv")
    assert {row["metric"] for row in rows} == {
        "delay_median_ms",
        "jitter_mean_ms",
    }
    for row in rows:
        assert row["quality"] == "estimator_candidate_unvalidated"
        assert row["n_steps"] == "4"
        assert row["n_finite"] == "4"
    # Constant rtt 20 ms one-way factor 0.5, under capacity (no queue
    # drain): per-step delay is exactly 10.0 ms; constant series carries
    # zero trace jitter and no disruption, so jitter is exactly 0.0.
    for row in rows:
        if row["metric"] == "delay_median_ms":
            assert float(row["value"]) == pytest.approx(10.0)
        else:
            assert float(row["value"]) == pytest.approx(0.0)
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["estimator_csv"] == "emulator_estimator.csv"
    for window in manifest["windows"]:
        assert window["end_residual_occupancy_bytes"] == 0.0
    proposed = manifest["capacity_convention_proposed"]
    assert proposed["applied"] is False
    assert proposed["scale_factor"] == pytest.approx(1400.0 / 1442.0)


def test_estimator_candidate_saturation_and_residual_boundary(tmp_path):
    scenario = _write_scenario(tmp_path, rate_mbps=200.0, capacity_mbps=100.0)
    out = tmp_path / "out"
    code = run_case(
        scenario, out_dir=out, required_metrics=["delay_median_ms"]
    )
    assert code == 2
    rows = _read_csv(out / "emulator_estimator.csv")
    assert len(rows) == 2  # 2 reps
    for row in rows:
        # Queue drain adds to the 10 ms base delay under saturation.
        assert float(row["value"]) > 10.0
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    for window in manifest["windows"]:
        # Saturated queue stays non-empty at episode end: the boundary
        # term is nonzero and reported.
        assert window["end_residual_occupancy_bytes"] > 0.0


def test_no_estimator_file_when_not_required(tmp_path):
    scenario = _write_scenario(tmp_path)
    out = tmp_path / "out"
    code = run_case(scenario, out_dir=out, required_metrics=["loss_frac"])
    assert code == 0
    assert not (out / "emulator_estimator.csv").exists()
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["estimator_csv"] is None


def test_matched_mode_metric_determinism_across_seeds(tmp_path):
    # D6 protocol: matched mode must be metric-deterministic; verified by
    # running two seeds and requiring bit-identical numeric row values
    # (string equality on repr), not by code inspection alone.
    scenario = _write_scenario(tmp_path, rate_mbps=200.0, capacity_mbps=100.0)
    tables = []
    for seed in (0, 1):
        out = tmp_path / f"out{seed}"
        code = run_case(
            scenario,
            out_dir=out,
            seed=seed,
            required_metrics=["loss_frac", "throughput_mbps"],
        )
        assert code == 0
        tables.append(_read_csv(out / "emulator_metrics.csv"))
    assert len(tables[0]) == len(tables[1])
    for row_a, row_b in zip(*tables):
        assert row_a["metric"] == row_b["metric"]
        assert row_a["value"] == row_b["value"]
