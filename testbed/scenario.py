"""Scenario definitions and OpenFlow selectors for the SD-WAN testbed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathSpec:
    name: str
    capacity_mbps: float
    one_way_delay_ms: float
    jitter_ms: float
    loss_pct: float

    @property
    def rtt_ms(self) -> float:
        return 2.0 * self.one_way_delay_ms


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    flow_type: str
    transport: str
    client_ip: str
    server_port: int
    rate_mbps: float
    duration_s: float
    warmup_s: float
    packet_bytes: int


@dataclass(frozen=True)
class SwitchEvent:
    workload: str
    old_path: str
    new_path: str


@dataclass(frozen=True)
class Scenario:
    name: str
    server_ip: str
    paths: dict[str, PathSpec]
    workloads: dict[str, WorkloadSpec]
    events: tuple[SwitchEvent, ...]
    repetitions: int = 1
    queue_limit_packets: int = 1000
    per_path_queue_limit_packets: dict[str, int] | None = None
    branch_profile: str = "medium"
    workload_regime: str = "normal"

    def queue_limit_for(self, path: str) -> int:
        """Per-path queue limit for engine matching, else the scenario one.

        Matched comparisons with the emulator want buffer bytes =
        capacity * queue_buffer_s per path; the shared single limit is
        kept as the default for simple smoke scenarios.
        """

        if self.per_path_queue_limit_packets and path in self.per_path_queue_limit_packets:
            return int(self.per_path_queue_limit_packets[path])
        return self.queue_limit_packets


def load_scenario(path: str | Path) -> Scenario:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    paths = {name: PathSpec(name=name, **spec) for name, spec in raw["paths"].items()}
    workloads = {
        name: WorkloadSpec(name=name, **spec) for name, spec in raw["workloads"].items()
    }
    events = tuple(SwitchEvent(**event) for event in raw["events"])
    scenario = Scenario(
        name=raw["name"],
        server_ip=raw["server_ip"],
        paths=paths,
        workloads=workloads,
        events=events,
        repetitions=int(raw.get("repetitions", 1)),
        queue_limit_packets=int(raw.get("queue_limit_packets", 1000)),
        per_path_queue_limit_packets=raw.get("per_path_queue_limit_packets"),
        branch_profile=raw.get("branch_profile", "medium"),
        workload_regime=raw.get("workload_regime", "normal"),
    )
    validate_scenario(scenario)
    return scenario


def validate_scenario(scenario: Scenario) -> None:
    if not scenario.paths:
        raise ValueError("scenario must define at least one path")
    if scenario.repetitions < 1:
        raise ValueError("repetitions must be positive")
    if scenario.queue_limit_packets < 1:
        raise ValueError("queue_limit_packets must be positive")
    if scenario.branch_profile not in {"small", "medium", "large"}:
        raise ValueError("branch_profile must be small, medium, or large")
    if scenario.workload_regime not in {"low", "normal", "peak", "stress"}:
        raise ValueError("workload_regime must be low, normal, peak, or stress")
    for path in scenario.paths.values():
        if path.capacity_mbps <= 0:
            raise ValueError(f"path {path.name} capacity must be positive")
        if path.one_way_delay_ms < 0 or path.jitter_ms < 0:
            raise ValueError(f"path {path.name} delay/jitter must be non-negative")
        if not 0 <= path.loss_pct < 100:
            raise ValueError(f"path {path.name} loss must be in [0, 100)")
    for workload in scenario.workloads.values():
        if workload.transport not in {"tcp", "udp"}:
            raise ValueError(f"workload {workload.name} has unsupported transport")
        if workload.rate_mbps <= 0 or workload.duration_s <= 0:
            raise ValueError(f"workload {workload.name} rate/duration must be positive")
        if workload.warmup_s < 0 or workload.warmup_s >= workload.duration_s:
            raise ValueError(f"workload {workload.name} has invalid warmup")
        if workload.packet_bytes < 32:
            raise ValueError(f"workload {workload.name} packet is too small")
    for event in scenario.events:
        if event.workload not in scenario.workloads:
            raise ValueError(f"event references unknown workload {event.workload}")
        for path in (event.old_path, event.new_path):
            if path not in scenario.paths:
                raise ValueError(f"event references unknown path {path}")
        if event.old_path == event.new_path:
            raise ValueError("switch event must change paths")


def selector(workload: WorkloadSpec, server_ip: str) -> str:
    """OpenFlow match fields shared by forward and reverse class flows."""

    proto = workload.transport
    return f"ip,nw_dst={server_ip},{proto},tp_dst={workload.server_port}"


def reverse_selector(workload: WorkloadSpec, server_ip: str) -> str:
    return f"ip,nw_src={server_ip},{workload.transport},tp_src={workload.server_port}"


def route_flows(
    scenario: Scenario,
    event: SwitchEvent,
    path: str,
    *,
    path_port: int,
    client_port: int,
    server_port: int,
) -> dict[str, tuple[str, dict[str, str]]]:
    """Return switch flows needed for one active class route.

    Keys identify stable logical flow names so a later update can modify the
    same OpenFlow entries rather than delete and recreate them.
    """

    workload = scenario.workloads[event.workload]
    forward = selector(workload, scenario.server_ip)
    reverse = reverse_selector(workload, scenario.server_ip)
    return {
        "branch-forward": (
            "s_branch",
            {
                "match": forward,
                "actions": f"output:{path_port}",
            },
        ),
        "branch-reverse": (
            "s_branch",
            {
                "match": reverse,
                "actions": f"output:{client_port}",
            },
        ),
        "hub-in": (
            "s_hub",
            {
                "match": forward,
                "actions": f"output:{server_port}",
            },
        ),
        "hub-reverse": (
            "s_hub",
            {
                "match": reverse,
                "actions": f"output:{path_port}",
            },
        ),
    }
