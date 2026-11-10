"""Run repeatable Mininet switch experiments and write raw measurements.

Dry-run:

    .venv/bin/python -m testbed.run_switch_calibration \
        --scenario testbed/scenarios/smoke.json --dry-run

Execution uses the system Python because Mininet is installed outside the
project virtual environment:

    sudo env PYTHONPATH="$PWD" /usr/bin/python3 -m \
        testbed.run_switch_calibration --scenario testbed/scenarios/smoke.json

The output is raw, unvalidated testbed evidence. It does not populate the
emulator calibration by itself.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from testbed.analyze import (
    parse_qdisc_backlog_bytes,
    summarize_pcap,
    summarize_traffic,
)
from testbed.scenario import Scenario, SwitchEvent, load_scenario

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC_SCRIPT = ROOT / "testbed" / "traffic.py"

CALIBRATION_COLUMNS = (
    "old_rtt_ms",
    "new_rtt_ms",
    "old_jitter_ms",
    "new_jitter_ms",
    "packets_in_flight",
    "flow_type",
    "transport",
    "queue_occupancy_frac",
    "interruption_s",
    "loss_frac",
    "reordering_frac",
)


@dataclass(frozen=True)
class RunPlan:
    run_id: str
    event_index: int
    repetition: int
    workload: str
    old_path: str
    new_path: str
    directory: str


def build_run_plan(
    scenario: Scenario,
    output_dir: Path,
    *,
    repetitions: int | None = None,
) -> list[RunPlan]:
    repeats = scenario.repetitions if repetitions is None else repetitions
    if repeats < 1:
        raise ValueError("repetitions must be positive")
    plan = []
    for event_index, event in enumerate(scenario.events):
        for repetition in range(repeats):
            run_id = f"e{event_index:02d}-r{repetition:02d}"
            plan.append(
                RunPlan(
                    run_id=run_id,
                    event_index=event_index,
                    repetition=repetition,
                    workload=event.workload,
                    old_path=event.old_path,
                    new_path=event.new_path,
                    directory=str(output_dir / run_id),
                )
            )
    return plan


def tool_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0], "platform": platform.platform()}
    commands = {
        "mininet": ["mn", "--version"],
        "openvswitch": ["ovs-vsctl", "--version"],
        "tc": ["tc", "-V"],
        "tcpdump": ["tcpdump", "--version"],
        "tshark": ["tshark", "--version"],
    }
    for name, command in commands.items():
        if shutil.which(command[0]) is None:
            versions[name] = "missing"
            continue
        try:
            output = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            text = (output.stdout or output.stderr).splitlines()
            versions[name] = text[0] if text else "unknown"
        except (OSError, subprocess.TimeoutExpired) as exc:
            versions[name] = f"error: {exc}"
    return versions


def environment_checks(system_python: str = "/usr/bin/python3") -> list[str]:
    issues = []
    for command in ("mn", "ovs-vsctl", "ovs-ofctl", "tc", "tcpdump", "tshark"):
        if shutil.which(command) is None:
            issues.append(f"missing executable: {command}")
    probe = subprocess.run(
        [
            system_python,
            "-c",
            ("import mininet, sys; print(sys.executable); print(mininet.__file__)"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip()
        issues.append(f"{system_python} cannot import Mininet: {detail}")
    return issues


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def start_background(node, command: list[str], stdout_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    shell_command = " ".join(shlex.quote(part) for part in command)
    result = node.cmd(
        f"nohup {shell_command} > {shlex.quote(str(stdout_path))} 2>&1 & echo $!"
    )
    try:
        return int(result.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(
            f"could not start command on {node.name}: {shell_command}: {result}"
        ) from exc


def stop_background(node, pid: int, *, signal: str = "TERM") -> None:
    node.cmd(f"kill -{signal} {pid} 2>/dev/null || true")


def traffic_command(
    workload,
    role: str,
    output: Path,
    *,
    host: str,
    timeout_s: float,
) -> list[str]:
    return [
        sys.executable,
        str(TRAFFIC_SCRIPT),
        role,
        workload.transport,
        "--host",
        host,
        "--port",
        str(workload.server_port),
        "--rate-mbps",
        str(workload.rate_mbps),
        "--duration",
        str(workload.duration_s),
        "--timeout",
        str(timeout_s),
        "--idle-timeout",
        "2",
        "--packet-bytes",
        str(workload.packet_bytes),
        "--out",
        str(output),
    ]


def capture_command(interface: str, pcap: Path, workload) -> list[str]:
    return [
        "tcpdump",
        "-U",
        "-i",
        interface,
        "-n",
        "-s",
        "128",
        "-w",
        str(pcap),
        f"{workload.transport} port {workload.server_port}",
    ]


def run_one(
    testbed,
    scenario: Scenario,
    plan: RunPlan,
    *,
    event: SwitchEvent,
    capture: bool,
) -> dict:
    workload = scenario.workloads[event.workload]
    client = testbed.clients[workload.flow_type]
    server = testbed.server
    output_dir = Path(plan.directory)
    output_dir.mkdir(parents=True, exist_ok=False)

    testbed.clear_class_route()
    testbed.install_route(event, event.old_path)
    timeout_s = workload.duration_s + 8.0
    server_log = output_dir / "receiver.csv"
    sender_log = output_dir / "sender.csv"
    server_stdout = output_dir / "receiver.log"
    sender_stdout = output_dir / "sender.log"
    pcap_path = output_dir / "traffic.pcap"
    qdisc_before_path = output_dir / "qdisc_before.txt"
    qdisc_after_path = output_dir / "qdisc_after.txt"

    capture_pid = None
    server_pid = start_background(
        server,
        traffic_command(
            workload,
            "receiver",
            server_log,
            host="0.0.0.0",
            timeout_s=timeout_s,
        ),
        server_stdout,
    )
    if capture:
        capture_pid = start_background(
            server,
            capture_command(server.defaultIntf().name, pcap_path, workload),
            output_dir / "tcpdump.log",
        )
    time.sleep(0.6)
    sender_pid = start_background(
        client,
        traffic_command(
            workload,
            "sender",
            sender_log,
            host=scenario.server_ip,
            timeout_s=timeout_s,
        ),
        sender_stdout,
    )

    time.sleep(workload.warmup_s)
    qdisc_before = testbed.qdisc_stats(event.old_path)
    qdisc_before_path.write_text(qdisc_before, encoding="utf-8")
    switch_started = time.monotonic()
    testbed.modify_route(event, event.new_path)
    route_update_s = time.monotonic() - switch_started
    remaining = max(0.0, workload.duration_s - workload.warmup_s)
    time.sleep(remaining + 2.5)
    qdisc_after = testbed.qdisc_stats(event.new_path)
    qdisc_after_path.write_text(qdisc_after, encoding="utf-8")

    if capture_pid is not None:
        stop_background(server, capture_pid, signal="INT")
    stop_background(server, server_pid)
    stop_background(client, sender_pid)
    time.sleep(0.5)

    traffic = summarize_traffic(
        sender_log,
        server_log,
        packet_bytes=workload.packet_bytes,
        switch_at_s=switch_started,
    )
    pcap = summarize_pcap(pcap_path)
    old_path = scenario.paths[event.old_path]
    new_path = scenario.paths[event.new_path]
    # The backlog sits on the old path's qdisc, whose limit is the
    # per-path value when configured; convert the packet limit to bytes
    # with the workload's actual packet size, not a fixed 1500.
    queue_limit_bytes = (
        scenario.queue_limit_for(event.old_path) * workload.packet_bytes
    )
    old_backlog = parse_qdisc_backlog_bytes(qdisc_before)
    packets_in_flight = max(
        1.0,
        workload.rate_mbps
        * 1e6
        * old_path.rtt_ms
        / 1000.0
        / (workload.packet_bytes * 8.0),
    )
    transport_loss = traffic["loss_frac"]
    if workload.transport == "tcp" and pcap["tcp_data_packets"]:
        transport_loss = max(
            transport_loss,
            pcap["tcp_retransmissions"] / pcap["tcp_data_packets"],
        )
    reordering = traffic["reordering_frac"]
    if workload.transport == "tcp" and pcap["tcp_data_packets"]:
        reordering = pcap["tcp_out_of_order"] / pcap["tcp_data_packets"]

    metrics = {
        "run_id": plan.run_id,
        "scenario": scenario.name,
        "branch_profile": scenario.branch_profile,
        "workload_regime": scenario.workload_regime,
        "event_index": plan.event_index,
        "repetition": plan.repetition,
        "workload": workload.name,
        "flow_type": workload.flow_type,
        "transport": workload.transport,
        "old_path": event.old_path,
        "new_path": event.new_path,
        "old_rtt_ms": old_path.rtt_ms,
        "new_rtt_ms": new_path.rtt_ms,
        "old_jitter_ms": old_path.jitter_ms,
        "new_jitter_ms": new_path.jitter_ms,
        "packets_in_flight": packets_in_flight,
        "queue_occupancy_frac": min(old_backlog / queue_limit_bytes, 1.0),
        "interruption_s": traffic["interruption_s"],
        "loss_frac": transport_loss,
        "reordering_frac": reordering,
        "route_update_s": route_update_s,
        "delay_median_ms": traffic["delay_median_ms"],
        "delay_p95_ms": traffic["delay_p95_ms"],
        "jitter_mean_ms": traffic["jitter_mean_ms"],
        "throughput_mbps": traffic["throughput_mbps"],
        "sent_frames": traffic["sent_frames"],
        "received_frames": traffic["received_frames"],
        "received_near_switch": traffic["received_near_switch"],
        "tcp_data_packets": pcap["tcp_data_packets"],
        "tcp_retransmissions": pcap["tcp_retransmissions"],
        "tcp_out_of_order": pcap["tcp_out_of_order"],
        "old_path_capacity_mbps": old_path.capacity_mbps,
        "new_path_capacity_mbps": new_path.capacity_mbps,
        "old_path_loss_pct": old_path.loss_pct,
        "new_path_loss_pct": new_path.loss_pct,
        "rule_update_method": "ovs-ofctl-openflow13-mod-flows",
        "quality_status": "raw_unvalidated",
    }
    write_json(output_dir / "metrics.json", metrics)
    return metrics


def run_actual(scenario: Scenario, plan: list[RunPlan], capture: bool) -> list[dict]:
    if os.geteuid() != 0:
        raise PermissionError("Mininet execution must run with sudo")
    issues = environment_checks()
    if issues:
        raise RuntimeError("; ".join(issues))

    from testbed.sdwan_topology import build_network

    testbed = build_network(scenario).start()
    results = []
    try:
        for item in plan:
            event = scenario.events[item.event_index]
            print(
                f"[{item.run_id}] {event.workload} {event.old_path}->{event.new_path}",
                flush=True,
            )
            results.append(
                run_one(
                    testbed,
                    scenario,
                    item,
                    event=event,
                    capture=capture,
                )
            )
    finally:
        testbed.stop()
    return results


def write_results(output_dir: Path, scenario_path: Path, results: list[dict]) -> None:
    if not results:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "switch_metrics_raw.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    manifest = {
        "status": "raw_unvalidated",
        "scenario_path": str(scenario_path),
        "scenario_sha256": hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
        "created_utc": datetime.now(UTC).isoformat(),
        "runs": len(results),
        "calibration_columns": list(CALIBRATION_COLUMNS),
        "tool_versions": tool_versions(),
        "note": (
            "Raw testbed output only. Do not enable switching calibration or "
            "claim cross-engine validation until repeated runs are audited."
        ),
    }
    write_json(output_dir / "run_manifest.json", manifest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("testbed/outputs") / "smoke")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--no-capture", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    plan = build_run_plan(
        scenario,
        args.out,
        repetitions=args.repetitions,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out / "dry_run_plan.json",
        {
            "scenario": scenario.name,
            "branch_profile": scenario.branch_profile,
            "workload_regime": scenario.workload_regime,
            "runs": [asdict(item) for item in plan],
            "environment_checks": environment_checks(),
            "tool_versions": tool_versions(),
            "execution_environment": "/usr/bin/python3 (system Mininet)",
        },
    )
    print(json.dumps([asdict(item) for item in plan], indent=2))
    if args.dry_run:
        issues = environment_checks()
        if issues:
            print("Environment issues:", file=sys.stderr)
            for issue in issues:
                print(f"- {issue}", file=sys.stderr)
        print(f"dry-run manifest: {args.out / 'dry_run_plan.json'}")
        return

    results = run_actual(scenario, plan, capture=not args.no_capture)
    write_results(args.out, args.scenario, results)
    print(f"raw measurements: {args.out / 'switch_metrics_raw.csv'}")


if __name__ == "__main__":
    main()
