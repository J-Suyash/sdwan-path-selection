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
