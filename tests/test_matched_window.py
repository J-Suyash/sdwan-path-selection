import csv
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from testbed.matched_window import inspection_offsets, matched_window_spec, queue_snapshot, summarize_matched_window
from testbed.scenario import load_scenario


def test_shared_spec_and_grid():
    s = load_scenario("testbed/scenarios/case_drafts/ce01.json")
    w = next(iter(s.workloads.values()))
    spec = matched_window_spec(s, w)
    assert spec["max_episode_s"] == 19
    assert inspection_offsets(spec) == [15, 16, 17, 18, 19]
    assert "working interpretation" in spec["interpretation"]
    with pytest.raises(ValueError, match="1400"):
        matched_window_spec(s, replace(w, packet_bytes=1200))
    with pytest.raises(ValueError, match="integer"):
        inspection_offsets({**spec, "send_duration_s": 14.5})


def test_snapshot_avoids_parent_child_double_count_and_fails_closed():
    text = "backlog 1442b 1p requeues 0\nbacklog 1442b 1p requeues 0"
    r = queue_snapshot({"a": text, "b": "backlog 0b 0p requeues 0"})
    assert r["summed_wire_backlog_bytes"] == 1442
    assert r["drained"] is False
    assert queue_snapshot({"a": "backlog 0b 0p requeues 0"})["drained"] is True
    assert queue_snapshot({"a": "backlog 0b 1p requeues 0"})["drained"] is False
    for texts in [{}, {"a": "tc command failed"}]:
        with pytest.raises(ValueError):
            queue_snapshot(texts)


def write_log(p, times):
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "sent_at", "received_at"])
        w.writerows((i, t, t) for i, t in times)


def test_summary_filters_late_arrivals_and_reports_not_hides_them(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_log(a, [(0, 10), (1, 11), (2, 12), (3, 17)])
    write_log(b, [(0, 10.1), (1, 16), (2, 12.1), (3, 17.1)])
    r = summarize_matched_window(a, b, t0=10, t1=15, packet_bytes=1400)
    assert r["sent_frames"] == 3
    assert r["received_frames"] == 2
    assert r["sent_frames_outside_window"] == 1
    assert r["received_frames_after_window"] == 1
    assert r["app_loss_frac"] == pytest.approx(1/3)
    assert r["app_payload_throughput_mbps"] == pytest.approx(2 * 1400 * 8 / 5e6)
    with pytest.raises(ValueError):
        summarize_matched_window(a, b, t0=15, t1=10, packet_bytes=1400)


def test_runner_opt_in_path_without_mininet(tmp_path, monkeypatch):
    import testbed.run_switch_calibration as m
    s = load_scenario("testbed/scenarios/case_drafts/ce01.json")
    plan = m.build_run_plan(s, tmp_path / "run", repetitions=1)[0]
    now = [99.4]
    def sleep(dt):
        assert dt >= 0
        now[0] += dt
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=lambda: now[0], time=lambda: now[0] + 10000, sleep=sleep))
    def start(node, command, log):
        p = Path(command[command.index("--out") + 1])
        if "sender" in command:
            write_log(p, [(0, 100), (1, 101)])
            marker = Path(command[command.index("--start-marker") + 1])
            marker.write_text(json.dumps({"first_sent_monotonic_s": 100}))
        else:
            write_log(p, [(0, 100.1), (1, 101.1)])
            assert float(command[command.index("--idle-timeout") + 1]) > 19
        return 1
    monkeypatch.setattr(m, "start_background", start)
    monkeypatch.setattr(m, "stop_background", lambda *a, **k: None)
    monkeypatch.setattr(m, "summarize_pcap", lambda p: {"tcp_data_packets": 0, "tcp_retransmissions": 0, "tcp_out_of_order": 0})
    qcalls = []
    def qdisc(p):
        qcalls.append(p)
        return "backlog 0b 0p requeues 0"
    tb = SimpleNamespace(clients={"bulk": object()}, server=object(), clear_class_route=lambda: None,
                         install_route=lambda *a: None, set_path_capacity=lambda *a: None, qdisc_stats=qdisc)
    r = m.run_one(tb, s, plan, event=s.events[0], capture=False, matched_drain=True)
    endpoint = json.loads((Path(plan.directory) / "matched_window.json").read_text())
    assert endpoint["drain_termination"] == "drained"
    assert endpoint["t1_monotonic_s"] == 115
    assert endpoint["application_summary"]["measurement_window_s"] == 15
    assert endpoint["actual_event_offset_s"] == 6
    assert set(endpoint["inspections"][0]["paths"]) == set(s.paths)
    assert endpoint["application_summary"]["app_loss_frac"] == 0
    # Legacy output remains its original first-to-last-arrival calculation.
    assert r["throughput_mbps"] != endpoint["application_summary"]["app_payload_throughput_mbps"]


def test_traffic_command_marker_and_legacy_defaults(tmp_path):
    from testbed.run_switch_calibration import traffic_command
    s = load_scenario("testbed/scenarios/case_drafts/ce01.json")
    w = next(iter(s.workloads.values()))
    old = traffic_command(w, "sender", tmp_path / "out", host="127.0.0.1", timeout_s=22)
    assert "--start-marker" not in old
    assert old[old.index("--idle-timeout") + 1] == "2.0"
    new = traffic_command(w, "sender", tmp_path / "out", host="127.0.0.1", timeout_s=29,
                          start_marker=tmp_path / "marker", idle_timeout_s=29)
    assert new[new.index("--start-marker") + 1] == str(tmp_path / "marker")
    assert new[new.index("--idle-timeout") + 1] == "29"
