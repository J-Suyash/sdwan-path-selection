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

class _FakeIntf:
    """Records issued shell commands; no tc execution."""

    def __init__(self, name):
        self.name = name
        self.cmds = []

    def cmd(self, command):
        self.cmds.append(command)
        return ""


class _FakeLink:
    def __init__(self):
        self.intf1 = _FakeIntf("branch-eth2")
        self.intf2 = _FakeIntf("hub-eth2")


def _install_mininet_stub():
    """sdwan_topology imports mininet, which only exists in the system
    python. These unit tests exercise pure-python command construction, so
    a stub package with placeholder classes is enough - no Mininet runtime.
    """
    import sys
    import types

    if "mininet" in sys.modules:
        return
    package = types.ModuleType("mininet")
    package.__path__ = []
    sys.modules["mininet"] = package
    for name, attrs in {
        "mininet.cli": ["CLI"],
        "mininet.link": ["TCLink"],
        "mininet.net": ["Mininet"],
        "mininet.node": ["Controller", "OVSSwitch"],
    }.items():
        module = types.ModuleType(name)
        for attr in attrs:
            setattr(module, attr, type(attr, (), {}))
        sys.modules[name] = module


def _bare_testbed(path_links):
    _install_mininet_stub()
    from testbed.sdwan_topology import TestbedNetwork

    testbed = object.__new__(TestbedNetwork)
    object.__setattr__(testbed, "scenario", load_scenario(
        "testbed/scenarios/smoke.json"))
    object.__setattr__(testbed, "path_links", path_links)
    return testbed


def test_set_path_capacity_changes_tbf_in_place_on_both_interfaces():
    link = _FakeLink()
    testbed = _bare_testbed({"five_g": link})
    testbed.set_path_capacity("five_g", 30.0)
    for intf in (link.intf1, link.intf2):
        assert len(intf.cmds) == 1
        cmd = intf.cmds[0]
        # in-place rate change: never delete/rebuild the root qdisc, so
        # backlog queued before the sag survives the capacity change
        assert "qdisc change" in cmd
        assert "qdisc del" not in cmd
        assert "root handle 5:" in cmd
        assert "rate 30.0Mbit" in cmd
        # burst/latency mirror TCIntf.bwCmds: burst 15000, latency 120/bw ms
        assert "burst 15000" in cmd
        assert "latency 4.0ms" in cmd
        assert cmd.startswith(f"tc qdisc change dev {intf.name} ")


def test_set_path_capacity_raises_on_tc_error():
    class _BadIntf(_FakeIntf):
        def cmd(self, command):
            return "RTNETLINK answers: No such file or directory"

    link = _FakeLink()
    link.intf1 = _BadIntf("branch-eth2")
    testbed = _bare_testbed({"five_g": link})
    with pytest.raises(RuntimeError, match="capacity change failed"):
        testbed.set_path_capacity("five_g", 30.0)


def test_set_path_capacity_unknown_path_raises_keyerror():
    testbed = _bare_testbed({"five_g": _FakeLink()})
    with pytest.raises(KeyError):
        testbed.set_path_capacity("bb", 10.0)

