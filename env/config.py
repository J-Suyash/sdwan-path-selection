"""Configuration for the SD-WAN emulator.

Values in this module are experiment defaults and explicit assumptions, not
empirical enterprise-wide parameters. Evidence and confidence are tracked in
``docs/parameter_registry.csv``.
"""

import math
from dataclasses import dataclass, field

from env.workload import DEFAULT_BRANCH_PROFILES, BranchProfile


@dataclass
class SDWanConfig:
    # Topology
    underlays: tuple[str, ...] = ("bb", "five_g", "leo")
    classes: tuple[str, ...] = ("voice", "video", "interactive", "bulk")
    decision_interval_s: float = 1.0
    episode_seconds: int = 3600
    history_s: int = 10

    # Workload scenario. The profile is intentionally configurable; there is
    # no universal enterprise population or daily curve.
    branch_profiles: dict[str, BranchProfile] = field(
        default_factory=lambda: dict(DEFAULT_BRANCH_PROFILES)
    )
    primary_profile: str = "medium"
    workload_regime: str | None = None

    # Link speeds (capacity caps, Mbps)
    cap_mbps: dict[str, float] = field(
        default_factory=lambda: {"bb": 200.0, "five_g": 300.0, "leo": 200.0}
    )

    # Prices (per GB, model parameters per Section 11.4)
    price_per_gb: dict[str, float] = field(
        default_factory=lambda: {"bb": 0.02, "five_g": 0.15, "leo": 0.08}
    )

    # SLA thresholds per class: delay ms, jitter ms, loss fraction
    sla: dict[str, tuple[float, float, float]] = field(
        default_factory=lambda: {
            "voice": (150.0, 30.0, 0.01),
            "video": (150.0, 40.0, 0.02),
            "interactive": (200.0, 50.0, 0.05),
            "bulk": (float("inf"), float("inf"), 1.0),
        }
    )

    # Violation budgets per class (fraction of seconds allowed) and
    # switch budget (switches per minute per class)
    epsilon: dict[str, float] = field(
        default_factory=lambda: {
            "voice": 0.01,
            "video": 0.02,
            "interactive": 0.03,
            "bulk": 1.0,
        }
    )
    max_switches_per_min: float = 2.0

    # Legacy scalar traffic inputs retained for compatibility with older
    # experiments. The hierarchical WorkloadGenerator is the active model.
    voice_call_kbps: float = 64.0
    voice_calls: tuple[int, int] = (3, 12)
    video_mbps: tuple[float, float] = (1.0, 4.0)
    interactive_mbps: tuple[float, float] = (0.5, 3.0)
    bulk_mbps: tuple[float, float] = (5.0, 30.0)

    # Bounded fluid queue approximation. The buffer is expressed as seconds
    # of nominal capacity so it scales across underlays.
    queue_buffer_s: float = 0.25
    queue_discipline: str = "fifo-fluid"
    transport_approximation: str = "fluid-rate-v1"

    # No switching transient is assumed without measured calibration rows.
    # See data/switching_calibration_template.csv and docs/workload_model_spec.md.
    switching_calibration_path: str | None = None

    # Trace handling
    data_root: str = "data/processed"
    underlay_source: dict[str, str] = field(
        default_factory=lambda: {
            "bb": "collected",
            "five_g": "lumos5g",
            "leo": "wetlinks",
        }
    )
    fallback_rtt_ms: dict[str, float] = field(
        default_factory=lambda: {"bb": 30.0, "five_g": 40.0, "leo": 60.0}
    )

    def __post_init__(self) -> None:
        if self.primary_profile not in self.branch_profiles:
            raise ValueError(
                f"unknown primary_profile {self.primary_profile!r}; "
                f"choose from {sorted(self.branch_profiles)}"
            )
        if self.decision_interval_s <= 0 or self.episode_seconds <= 0:
            raise ValueError("decision_interval_s and episode_seconds must be positive")
        steps = self.episode_seconds / self.decision_interval_s
        if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                "episode_seconds must be an integer multiple of decision_interval_s"
            )
        if self.queue_buffer_s < 0:
            raise ValueError("queue_buffer_s must be non-negative")
        if self.workload_regime not in {None, "low", "normal", "peak", "stress"}:
            raise ValueError(
                "workload_regime must be low, normal, peak, stress, or None"
            )

    @property
    def episode_steps(self) -> int:
        return round(self.episode_seconds / self.decision_interval_s)

    @property
    def episode_duration_s(self) -> float:
        return self.episode_steps * self.decision_interval_s

    @property
    def history_steps(self) -> int:
        return max(1, math.ceil(self.history_s / self.decision_interval_s))
