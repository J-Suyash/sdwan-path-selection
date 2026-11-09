import json

import pytest

from testbed.scenario import load_scenario, reverse_selector, route_flows, selector


def test_smoke_scenario_loads_and_builds_stable_flows():
    scenario = load_scenario("testbed/scenarios/smoke.json")
    event = scenario.events[0]
    workload = scenario.workloads[event.workload]
    flows = route_flows(
        scenario,
        event,
        event.old_path,
        path_port=2,
        client_port=6,
        server_port=5,
    )

    assert selector(workload, scenario.server_ip) == (
        "ip,nw_dst=10.0.0.100,udp,tp_dst=5004"
    )
    assert scenario.branch_profile == "medium"
    assert scenario.workload_regime == "normal"
    assert reverse_selector(workload, scenario.server_ip) == (
        "ip,nw_src=10.0.0.100,udp,tp_src=5004"
    )
    assert flows["branch-forward"][1]["actions"] == "output:2"
    assert flows["hub-in"][1]["match"] == selector(workload, scenario.server_ip)
    assert flows["hub-in"][1]["actions"] == "output:5"


def test_scenario_rejects_unknown_path(tmp_path):
    with open("testbed/scenarios/smoke.json", encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["events"][0]["new_path"] = "missing"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown path"):
        load_scenario(path)


def test_per_path_queue_limit_overrides_shared_limit(tmp_path):
    raw = {
        "name": "matched",
        "server_ip": "10.0.0.100",
        "paths": {
            "bb": {"capacity_mbps": 200, "one_way_delay_ms": 93.7,
                   "jitter_ms": 0.3, "loss_pct": 0},
            "leo": {"capacity_mbps": 100, "one_way_delay_ms": 31.0,
                    "jitter_ms": 0.3, "loss_pct": 0},
        },
        "workloads": {
            "voice": {"flow_type": "voice", "transport": "udp",
                      "client_ip": "10.0.0.11", "server_port": 5004,
                      "rate_mbps": 0.15, "duration_s": 10, "warmup_s": 4,
                      "packet_bytes": 240},
        },
        "events": [{"workload": "voice", "old_path": "bb", "new_path": "leo"}],
        "queue_limit_packets": 1000,
        # Emulator queue_buffer_s=0.25 scaled per capacity: bytes/1500.
        "per_path_queue_limit_packets": {"bb": 4166, "leo": 2083},
        "branch_profile": "medium",
        "workload_regime": "normal",
    }
    path = tmp_path / "matched.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    scenario = load_scenario(path)
    assert scenario.queue_limit_for("bb") == 4166
    assert scenario.queue_limit_for("leo") == 2083
    assert scenario.queue_limit_for("missing") == 1000  # shared fallback
