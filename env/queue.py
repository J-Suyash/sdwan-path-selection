"""Bounded fluid queue accounting used by the fast emulator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueueStep:
    offered_bytes: float
    admitted_bytes: float
    delivered_bytes: float
    dropped_bytes: float
    occupancy_bytes: float
    capacity_bytes: float


@dataclass
class FluidQueue:
    """FIFO fluid approximation; packet scheduling remains a testbed concern."""

    buffer_bytes: float
    occupancy_bytes: float = 0.0

    def __post_init__(self) -> None:
        if self.buffer_bytes < 0:
            raise ValueError("buffer_bytes must be non-negative")
        self.occupancy_bytes = min(
            max(float(self.occupancy_bytes), 0.0), self.buffer_bytes
        )

    def reset(self) -> None:
        self.occupancy_bytes = 0.0

    def step(self, offered_mbps: float, capacity_mbps: float, dt_s: float) -> QueueStep:
        if offered_mbps < 0 or capacity_mbps < 0 or dt_s < 0:
            raise ValueError("rates and dt_s must be non-negative")
        offered = float(offered_mbps) * 1e6 / 8.0 * float(dt_s)
        capacity = float(capacity_mbps) * 1e6 / 8.0 * float(dt_s)

        # Drain existing backlog first, then admit new traffic. This makes
        # overflow drops attributable to arrivals exactly once.
        served_backlog = min(self.occupancy_bytes, capacity)
        self.occupancy_bytes -= served_backlog
        service_left = capacity - served_backlog
        delivered_new = min(offered, service_left)
        queued_new = offered - delivered_new
        available = max(self.buffer_bytes - self.occupancy_bytes, 0.0)
        admitted_queued = min(queued_new, available)
        dropped = queued_new - admitted_queued
        self.occupancy_bytes += admitted_queued
        self.occupancy_bytes = min(max(self.occupancy_bytes, 0.0), self.buffer_bytes)
        delivered = served_backlog + delivered_new
        return QueueStep(
            offered_bytes=offered,
            admitted_bytes=delivered_new + admitted_queued,
            delivered_bytes=delivered,
            dropped_bytes=dropped,
            occupancy_bytes=self.occupancy_bytes,
            capacity_bytes=capacity,
        )
