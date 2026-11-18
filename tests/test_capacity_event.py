"""Capacity-event scaffolding tests (runner schema only; no Mininet, no validation)."""

import json

import pytest

from testbed.run_switch_calibration import build_run_plan, describe_event
from testbed.scenario import CapacityEvent, SwitchEvent, load_scenario


def _raw(events):
    return {
        "name": "cap-test",
        "server_ip": "10.0.0.100",
        "paths": {
            "bb": {"capacity_mbps": 200, "one_way_delay_ms": 93.7,
                   "jitter_ms": 0.3, "loss_pct": 0},
            "five_g": {"capacity_mbps": 150, "one_way_delay_ms": 37.5,
                       "jitter_ms": 1.0, "loss_pct": 0},
        },
        "workloads": {
            "bulk_udp_60": {"flow_type": "bulk", "transport": "udp",
                            "client_ip": "10.0.0.14", "server_port": 9999,
                            "rate_mbps": 60.0, "duration_s": 14,
                            "warmup_s": 6, "packet_bytes": 1400},
        },
        "events": events,
        "repetitions": 2,
    }


def _load(tmp_path, events):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_raw(events)), encoding="utf-8")
    return load_scenario(path)


def test_capacity_event_loads(tmp_path):
    scenario = _load(tmp_path, [
        {"workload": "bulk_udp_60", "path": "five_g", "capacity_mbps": 30.0},
    ])
    event = scenario.events[0]
    assert isinstance(event, CapacityEvent)
    assert event.path == "five_g"
    assert event.capacity_mbps == 30.0


def test_switch_event_still_default_without_capacity_field(tmp_path):
    scenario = _load(tmp_path, [
        {"workload": "bulk_udp_60", "old_path": "bb", "new_path": "five_g"},
    ])
    assert isinstance(scenario.events[0], SwitchEvent)


@pytest.mark.parametrize(
    "scenario_file",
    ["testbed/scenarios/switch_calibration_v1.json",
     "testbed/scenarios/switch_calibration_v2.json",
     "testbed/scenarios/smoke.json"],
)
def test_committed_scenarios_keep_pure_switch_events(scenario_file):
    scenario = load_scenario(scenario_file)
    assert scenario.events
    assert all(isinstance(e, SwitchEvent) for e in scenario.events)


def test_ambiguous_event_rejected(tmp_path):
    with pytest.raises(ValueError, match="unexpected fields"):
        _load(tmp_path, [
            {"workload": "bulk_udp_60", "old_path": "bb", "new_path": "five_g",
             "path": "five_g", "capacity_mbps": 30.0},
        ])


def test_capacity_event_unknown_path_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown path"):
        _load(tmp_path, [
            {"workload": "bulk_udp_60", "path": "missing", "capacity_mbps": 30.0},
        ])


def test_capacity_event_nonpositive_capacity_rejected(tmp_path):
    with pytest.raises(ValueError, match="capacity must be positive"):
        _load(tmp_path, [
            {"workload": "bulk_udp_60", "path": "five_g", "capacity_mbps": 0.0},
        ])


def test_capacity_event_unknown_workload_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown workload"):
        _load(tmp_path, [
            {"workload": "missing", "path": "five_g", "capacity_mbps": 30.0},
        ])


def test_run_plan_maps_capacity_event_to_single_path(tmp_path):
    scenario = _load(tmp_path, [
        {"workload": "bulk_udp_60", "path": "five_g", "capacity_mbps": 30.0},
    ])
    plan = build_run_plan(scenario, tmp_path)
    assert [item.run_id for item in plan] == ["e00-r00", "e00-r01"]
    assert all(item.old_path == "five_g" == item.new_path for item in plan)


def test_describe_event_both_kinds(tmp_path):
    scenario = _load(tmp_path, [
        {"workload": "bulk_udp_60", "path": "five_g", "capacity_mbps": 30.0},
        {"workload": "bulk_udp_60", "old_path": "bb", "new_path": "five_g"},
    ])
    capacity, switch = scenario.events
    assert describe_event(capacity) == "bulk_udp_60 five_g capacity->30.0Mbps"
    assert describe_event(switch) == "bulk_udp_60 bb->five_g"
