"""Opt-in matched-window bookkeeping. No acceptance rules or tolerances."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from testbed.scenario import CapacityEvent


def matched_window_spec(scenario, workload):
    if workload.packet_bytes != 1400:
        raise ValueError("1442-byte wire convention is supported only for this 1400-byte setup")
    capacities = [p.capacity_mbps for p in scenario.paths.values()]
    capacities += [e.capacity_mbps for e in scenario.events if isinstance(e, CapacityEvent)]
    payload_fraction = 1400 / 1442
    max_buffer = max(scenario.queue_limit_for(p) for p in scenario.paths) * 1400
    drain_bound = 3 * max_buffer / (min(capacities) * payload_fraction * 1e6 / 8)
    max_episode = math.ceil(workload.duration_s + drain_bound)
    return {
        "send_duration_s": workload.duration_s,
        "event_s": workload.warmup_s,
        "inspection_interval_s": 1.0,
        "max_episode_s": max_episode,
        "payload_packet_bytes": 1400,
        "wire_packet_bytes": 1442,
        "capacity_scale": payload_fraction,
        "drain_bound_s_unrounded": drain_bound,
        "interpretation": (
            "ce01 sustained capacity floor from event to end is a working interpretation, not recovered original intent"
            if any(isinstance(e, CapacityEvent) for e in scenario.events) else
            "existing switch inputs, no boundary coverage inferred from case name"
        ),
    }


def inspection_offsets(spec):
    # Same first post-load decision boundary as the emulator. Current
    # drafts have integer duration; reject fractional grids rather than
    # silently round a sender window.
    duration = spec["send_duration_s"]
    if not float(duration).is_integer():
        raise ValueError("matched drain currently requires integer-second send duration")
    return list(range(int(duration) + 1, int(spec["max_episode_s"]) + 1))


def queue_snapshot(qdisc_texts, wire_packet_bytes=1442):
    import re
    from testbed.analyze import parse_qdisc_backlog_bytes
    values = {}
    for name, text in qdisc_texts.items():
        # Unlike the legacy descriptive parser, absence is not zero here.
        # Duplicated parent/child backlogs represent propagation, not two
        # queues to add. Retain max per path, then sum distinct paths.
        if not re.search(r"backlog\s+\S+\s+\d+p", text):
            raise ValueError(f"missing packet backlog on {name}")
        packets = max(int(v) for v in re.findall(r"backlog\s+\S+\s+(\d+)p", text))
        values[name] = {"wire_backlog_bytes": parse_qdisc_backlog_bytes(text), "backlog_packets": packets}
    if not values:
        raise ValueError("no qdisc paths inspected")
    return {
        "paths": values,
        "summed_wire_backlog_bytes": sum(v["wire_backlog_bytes"] for v in values.values()),
        "drained": all(v["backlog_packets"] == 0 and v["wire_backlog_bytes"] < wire_packet_bytes for v in values.values()),
    }


def summarize_matched_window(sender, receiver, *, t0, t1, packet_bytes):
    if not t1 > t0:
        raise ValueError("matched window must have positive duration")
    def read(path):
        with Path(path).open(newline="") as f:
            return {int(r["seq"]): float(r["received_at"]) for r in csv.DictReader(f)}
    all_sent = read(sender)
    all_received = read(receiver)
    sent = {k: v for k, v in all_sent.items() if t0 <= v <= t1}
    arrived = {k: v for k, v in all_received.items() if k in sent and t0 <= v <= t1}
    n = len(sent)
    return {
        "t0_monotonic_s": t0, "t1_monotonic_s": t1,
        "measurement_window_s": t1 - t0,
        "sent_frames": n, "received_frames": len(arrived),
        "sent_frames_outside_window": len(all_sent) - n,
        "received_frames_after_window": sum(k in sent and v > t1 for k, v in all_received.items()),
        "app_loss_frac": 1 - len(arrived) / n if n else None,
        "app_payload_throughput_mbps": len(arrived) * packet_bytes * 8 / 1e6 / (t1 - t0),
        "basis": "application sequence logs, not capture or qdisc loss; packet-to-fluid equivalence not assumed",
    }
