"""Hierarchical, deterministic workload generation for the SD-WAN emulator.

The generator deliberately keeps workload levels separate:
branch profile -> user/device -> application session -> related flows.
It produces a fast fluid-rate snapshot for the Gymnasium environment while
retaining enough identity and lifecycle information to validate the model
against packet-level experiments.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

APP_CLASSES = ("voice", "video", "interactive", "bulk")


@dataclass(frozen=True)
class BranchProfile:
    """A scenario definition, not a claim about all enterprise branches."""

    name: str
    total_users: int
    devices_per_user: int = 1
    operating_hours: tuple[float, float] = (8.0, 18.0)
    active_user_fraction: dict[str, float] = field(
        default_factory=lambda: {
            "low": 0.15,
            "normal": 0.35,
            "peak": 0.7,
            "stress": 0.95,
        }
    )
    regime_multipliers: dict[str, float] = field(
        default_factory=lambda: {"low": 0.5, "normal": 1.0, "peak": 1.8, "stress": 2.5}
    )
    application_mix: dict[str, float] = field(
        default_factory=lambda: {
            "voice": 0.15,
            "video": 0.2,
            "interactive": 0.5,
            "bulk": 0.15,
        }
    )
    session_rate_per_active_user_min: dict[str, float] = field(
        default_factory=lambda: {
            "voice": 0.03,
            "video": 0.02,
            "interactive": 0.12,
            "bulk": 0.01,
        }
    )
    session_duration_s: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "voice": (30.0, 900.0),
            "video": (60.0, 1800.0),
            "interactive": (30.0, 600.0),
            "bulk": (30.0, 3600.0),
        }
    )

    def __post_init__(self) -> None:
        if self.total_users <= 0 or self.devices_per_user <= 0:
            raise ValueError("profile population must be positive")
        if not self.application_mix or any(
            v < 0 for v in self.application_mix.values()
        ):
            raise ValueError("application_mix must contain non-negative weights")
        if sum(self.application_mix.values()) <= 0:
            raise ValueError("application_mix must have a positive total")
        missing = set(APP_CLASSES) - set(self.application_mix)
        if missing:
            raise ValueError(f"application_mix missing classes: {sorted(missing)}")


DEFAULT_BRANCH_PROFILES = {
    # These are explicit experimental assumptions. Replace values only after
    # the parameter registry records evidence or a controlled measurement.
    "small": BranchProfile("small", total_users=10),
    "medium": BranchProfile("medium", total_users=25),
    "large": BranchProfile("large", total_users=75),
}


@dataclass(frozen=True)
class UserDevice:
    user_id: str
    device_id: str
    device_type: str = "workstation"


@dataclass
class Flow:
    flow_id: str
    session_id: str
    class_name: str
    direction: str
    transport: str
    start_s: float
    end_s: float
    rate_mbps: float
    response_to: str | None = None
    bytes_offered: float = 0.0
    terminated_s: float | None = None
    censored: bool = False

    @property
    def active(self) -> bool:
        return self.terminated_s is None


@dataclass
class ApplicationSession:
    session_id: str
    user: UserDevice
    class_name: str
    start_s: float
    end_s: float
    attributes: dict[str, float | str] = field(default_factory=dict)
    flow_ids: list[str] = field(default_factory=list)
    terminated_s: float | None = None
    censored: bool = False

    @property
    def active(self) -> bool:
        return self.terminated_s is None


@dataclass(frozen=True)
class WorkloadSnapshot:
    time_s: float
    offered_mbps: dict[str, float]
    offered_bytes: dict[str, float]
    active_users: int
    active_sessions: int
    active_flows: int
    started_sessions: int
    terminated_sessions: int
    censored_sessions: int
    terminated_flows: int
    censored_flows: int


class WorkloadGenerator:
    """Generate concurrent sessions and related flows with reproducible IDs."""

    def __init__(self, profile: BranchProfile, rng: np.random.Generator):
        self.profile = profile
        self.rng = rng
        self.users: list[UserDevice] = []
        self.sessions: dict[str, ApplicationSession] = {}
        self.flows: dict[str, Flow] = {}
        self._session_seq = 0
        self._flow_seq = 0
        self.start_hour = 8.0
        self.regime_override: str | None = None
        self.last_snapshot: WorkloadSnapshot | None = None

    def reset(self, start_hour: float = 8.0) -> None:
        self.start_hour = float(start_hour) % 24.0
        self.users = [
            UserDevice(f"user-{u:04d}", f"device-{u:04d}-{d:02d}")
            for u in range(self.profile.total_users)
            for d in range(self.profile.devices_per_user)
        ]
        self.sessions.clear()
        self.flows.clear()
        self._session_seq = 0
        self._flow_seq = 0
        self.last_snapshot = None

    def set_regime(self, regime: str | None) -> None:
        """Force a controlled regime for stress/generalisation experiments."""
        if regime is not None and regime not in {"low", "normal", "peak", "stress"}:
            raise ValueError("regime must be low, normal, peak, stress, or None")
        self.regime_override = regime

    def _regime(self, time_s: float) -> str:
        if self.regime_override is not None:
            return self.regime_override
        hour = (self.start_hour + time_s / 3600.0) % 24.0
        opening, closing = self.profile.operating_hours
        if not (opening <= hour < closing):
            return "low"
        fraction = (hour - opening) / max(closing - opening, 1e-9)
        if 0.4 <= fraction < 0.75:
            return "peak"
        return "normal"

    def _new_flow(
        self,
        session: ApplicationSession,
        direction: str,
        transport: str,
        start_s: float,
        end_s: float,
        rate_mbps: float,
        response_to: str | None = None,
    ) -> Flow:
        flow = Flow(
            flow_id=f"flow-{self._flow_seq:07d}",
            session_id=session.session_id,
            class_name=session.class_name,
            direction=direction,
            transport=transport,
            start_s=start_s,
            end_s=end_s,
            rate_mbps=max(float(rate_mbps), 0.0),
            response_to=response_to,
        )
        self._flow_seq += 1
        session.flow_ids.append(flow.flow_id)
        self.flows[flow.flow_id] = flow
        return flow

    def _make_session(
        self, time_s: float, class_name: str, user: UserDevice
    ) -> ApplicationSession:
        lo, hi = self.profile.session_duration_s[class_name]
        duration = float(self.rng.uniform(lo, hi))
        session = ApplicationSession(
            session_id=f"session-{self._session_seq:07d}",
            user=user,
            class_name=class_name,
            start_s=time_s,
            end_s=time_s + duration,
            attributes={"regime": self._regime(time_s)},
        )
        self._session_seq += 1
        self.sessions[session.session_id] = session

        if class_name == "voice":
            rate = float(self.rng.uniform(0.032, 0.08))
            self._new_flow(session, "uplink", "udp", time_s, session.end_s, rate)
            self._new_flow(session, "downlink", "udp", time_s, session.end_s, rate)
        elif class_name == "video":
            rate = float(self.rng.uniform(0.5, 4.0))
            self._new_flow(session, "uplink", "udp", time_s, session.end_s, rate)
            self._new_flow(
                session, "downlink", "udp", time_s, session.end_s, rate * 1.5
            )
        elif class_name == "interactive":
            request = self._new_flow(
                session, "uplink", "tcp", time_s, session.end_s, 0.05
            )
            self._new_flow(
                session,
                "downlink",
                "tcp",
                time_s,
                session.end_s,
                float(self.rng.uniform(0.1, 1.5)),
                response_to=request.flow_id,
            )
        else:
            size_mb = float(self.rng.lognormal(np.log(25.0), 1.0))
            self._new_flow(
                session,
                "uplink",
                "tcp",
                time_s,
                session.end_s,
                size_mb * 8.0 / max(duration, 1.0),
            )
        return session

    def _iter_active_flows(self, time_s: float) -> Iterator[Flow]:
        for flow in self.flows.values():
            if flow.active and flow.start_s <= time_s < flow.end_s:
                yield flow

    def advance(self, time_s: float, dt_s: float) -> WorkloadSnapshot:
        """Advance lifecycle state and return offered traffic for one step."""
        regime = self._regime(time_s)
        multiplier = self.profile.regime_multipliers.get(regime, 1.0)
        active_fraction = np.clip(
            self.profile.active_user_fraction.get(regime, 0.0), 0.0, 1.0
        )
        active_user_count = round(len(self.users) * active_fraction)
        active_user_count = min(max(active_user_count, 0), len(self.users))
        active_users = (
            self.rng.choice(self.users, size=active_user_count, replace=False)
            if active_user_count
            else []
        )

        started = 0
        if dt_s > 0 and active_user_count:
            mix_names = list(self.profile.application_mix)
            weights = np.asarray(
                [self.profile.application_mix[n] for n in mix_names], dtype=float
            )
            weights /= weights.sum()
            for user in active_users:
                total_rate = sum(
                    self.profile.session_rate_per_active_user_min.get(name, 0.0)
                    for name in mix_names
                )
                count = int(self.rng.poisson(total_rate * multiplier * dt_s / 60.0))
                for class_name in self.rng.choice(
                    mix_names, size=count, replace=True, p=weights
                ):
                    self._make_session(time_s, str(class_name), user)
                    started += 1

        terminated, terminated_flows = self._terminate_naturally(time_s)
        censored = 0
        censored_flows = 0

        offered_mbps = {name: 0.0 for name in APP_CLASSES}
        offered_bytes = {name: 0.0 for name in APP_CLASSES}
        active_flows = 0
        for flow in self._iter_active_flows(time_s):
            active_flows += 1
            offered_mbps[flow.class_name] += flow.rate_mbps
            bytes_now = flow.rate_mbps * 1e6 / 8.0 * max(dt_s, 0.0)
            flow.bytes_offered += bytes_now
            offered_bytes[flow.class_name] += bytes_now

        snapshot = WorkloadSnapshot(
            time_s=float(time_s),
            offered_mbps=offered_mbps,
            offered_bytes=offered_bytes,
            active_users=active_user_count,
            active_sessions=sum(s.active for s in self.sessions.values()),
            active_flows=active_flows,
            started_sessions=started,
            terminated_sessions=terminated,
            censored_sessions=censored,
            terminated_flows=terminated_flows,
            censored_flows=censored_flows,
        )
        self.last_snapshot = snapshot
        return snapshot

    def finalize(self, episode_end_s: float) -> dict[str, int]:
        """Separate natural completion from simulation-boundary censoring.

        Sessions and flows that complete on or before the final simulation
        instant are natural terminations. The rest are retained in the model
        with ``censored=True`` and are not mistaken for observed completions.
        """

        horizon = float(episode_end_s)
        terminated = 0
        terminated_flows = 0
        censored = 0
        censored_flows = 0
        for session in self.sessions.values():
            if not session.active:
                continue
            if session.end_s <= horizon:
                session.terminated_s = session.end_s
                terminated += 1
            else:
                session.terminated_s = horizon
                session.censored = True
                censored += 1
        for flow in self.flows.values():
            if not flow.active:
                continue
            if flow.end_s <= horizon:
                flow.terminated_s = flow.end_s
                terminated_flows += 1
            else:
                flow.terminated_s = horizon
                flow.censored = True
                censored_flows += 1
        return {
            "terminated_sessions": terminated,
            "censored_sessions": censored,
            "terminated_flows": terminated_flows,
            "censored_flows": censored_flows,
        }

    def lifecycle_report(self) -> dict[str, dict[str, int]]:
        """Return current totals without conflating completion and censoring."""

        return {
            "sessions": {
                "total": len(self.sessions),
                "active": sum(s.active for s in self.sessions.values()),
                "terminated": sum(
                    s.terminated_s is not None and not s.censored
                    for s in self.sessions.values()
                ),
                "censored": sum(s.censored for s in self.sessions.values()),
            },
            "flows": {
                "total": len(self.flows),
                "active": sum(f.active for f in self.flows.values()),
                "terminated": sum(
                    f.terminated_s is not None and not f.censored
                    for f in self.flows.values()
                ),
                "censored": sum(f.censored for f in self.flows.values()),
            },
        }

    def _terminate_naturally(self, time_s: float) -> tuple[int, int]:
        terminated = 0
        terminated_flows = 0
        for session in self.sessions.values():
            if session.active and time_s >= session.end_s:
                session.terminated_s = session.end_s
                terminated += 1
        for flow in self.flows.values():
            if flow.active and time_s >= flow.end_s:
                flow.terminated_s = flow.end_s
                terminated_flows += 1
        return terminated, terminated_flows
