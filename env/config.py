"""Configuration for the SD-WAN emulator.

All values follow the proposal (Sections 8.1, 8.2, 11.4) and are meant
to be overridden via Hydra later.
"""

from dataclasses import dataclass, field


@dataclass
class SDWanConfig:
    # Topology
    underlays: tuple[str, ...] = ("bb", "five_g", "leo")
    classes: tuple[str, ...] = ("voice", "video", "interactive", "bulk")
    decision_interval_s: float = 1.0
    episode_seconds: int = 3600
    history_s: int = 10

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

    # Traffic model (offered load, Mbps)
    voice_call_kbps: float = 64.0
    voice_calls: tuple[int, int] = (3, 12)
    video_mbps: tuple[float, float] = (1.0, 4.0)
    interactive_mbps: tuple[float, float] = (0.5, 3.0)
    bulk_mbps: tuple[float, float] = (5.0, 30.0)

    # Fluid-queue model (calibrated against Mininet in Phase 4)
    queue_scale_ms: float = 2.0
    overload_delay_ms: float = 150.0

    # Switching disruption: extra loss/jitter for 1-2 s after a switch
    disruption_s: int = 2
    disruption_loss: float = 0.01
    disruption_jitter_ms: float = 10.0

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
