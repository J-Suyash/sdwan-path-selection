"""Incumbent controllers: the rule-based policies that produce the
offline logs (proposal Section 10.2).

Every controller exposes `act(env)` -> joint action int and reads the
environment's history window to evaluate link quality.
"""

import numpy as np

from env.sdwan_env import SDWanEnv


class Incumbent:
    name = "incumbent"

    def reset(self, env: SDWanEnv) -> None:
        pass

    def act(self, env: SDWanEnv) -> int:
        raise NotImplementedError

    def _encode(self, env: SDWanEnv, assignment: dict[str, str]) -> int:
        action = 0
        for i, c in enumerate(env.cfg.classes):
            action += env.cfg.underlays.index(assignment[c]) * (env.K**i)
        return action


def link_ok(env: SDWanEnv, cls: str, underlay: str, scale: float = 1.0) -> bool:
    """A link satisfies a class SLA if its recent window stats clear the
    class thresholds (optionally scaled)."""
    hist = list(env.history[underlay])
    if not hist:
        return True
    mean_rtt = float(np.mean([h[0] for h in hist]))
    mean_jitter = float(np.mean([h[1] for h in hist]))
    mean_loss = float(np.mean([h[2] for h in hist]))
    up = bool(np.mean([h[4] for h in hist]) > 0.5)
    thr_d, thr_j, thr_l = env.cfg.sla[cls]
    return (
        up
        and mean_rtt <= thr_d * scale
        and mean_jitter <= max(thr_j * scale, 1.0)
        and mean_loss <= min(thr_l * scale, 1.0)
    )


def link_rtt(env: SDWanEnv, underlay: str) -> float:
    hist = list(env.history[underlay])
    return float(np.mean([h[0] for h in hist])) if hist else float("inf")


class ThresholdHysteresis(Incumbent):
    """Moves a class after N consecutive breach-seconds, waits M seconds
    before moving it again (proposal Section 10.2)."""

    def __init__(self, breach_n: int = 5, recover_m: int = 30, scale: float = 1.0):
        self.breach_n = breach_n
        self.recover_m = recover_m
        self.scale = scale
        self.name = f"threshold_n{breach_n}_m{recover_m}_s{scale}"

    def reset(self, env: SDWanEnv) -> None:
        self.breach = {c: 0 for c in env.cfg.classes}
        self.cooldown_until = {c: 0 for c in env.cfg.classes}

    def act(self, env: SDWanEnv) -> int:
        assignment = dict(env.assignment)
        for c in env.cfg.classes:
            if env.t < self.cooldown_until[c]:
                continue
            current = assignment[c]
            if not link_ok(env, c, current, self.scale):
                self.breach[c] += 1
            else:
                self.breach[c] = 0
                continue
            if self.breach[c] >= self.breach_n:
                candidates = [
                    u for u in env.cfg.underlays
                    if u != current and link_ok(env, c, u, self.scale)
                ]
                if candidates:
                    assignment[c] = min(candidates, key=lambda u: link_rtt(env, u))
                    self.breach[c] = 0
                    self.cooldown_until[c] = env.t + self.recover_m
        return self._encode(env, assignment)


class BestQuality(Incumbent):
    """Always sends each class over the lowest-latency link."""

    name = "best_quality"

    def act(self, env: SDWanEnv) -> int:
        assignment = {
            c: min(env.cfg.underlays, key=lambda u: link_rtt(env, u))
            for c in env.cfg.classes
        }
        return self._encode(env, assignment)


class LowestCostWithinSla(Incumbent):
    """Uses the cheapest link that currently meets the class SLA; falls
    back to best quality when none is compliant."""

    name = "lowest_cost"

    def act(self, env: SDWanEnv) -> int:
        assignment = {}
        for c in env.cfg.classes:
            compliant = [
                u for u in env.cfg.underlays if link_ok(env, c, u)
            ]
            if compliant:
                assignment[c] = min(
                    compliant, key=lambda u: env.cfg.price_per_gb[u]
                )
            else:
                assignment[c] = min(
                    env.cfg.underlays, key=lambda u: link_rtt(env, u)
                )
        return self._encode(env, assignment)


class EpsilonRandom(Incumbent):
    """Threshold policy that acts randomly epsilon fraction of the time
    (used for dataset D3 coverage)."""

    def __init__(self, epsilon: float = 0.1, rng: np.random.Generator | None = None):
        self.epsilon = epsilon
        self.rng = rng or np.random.default_rng(0)
        self.name = f"epsilon_{epsilon}"
        self.base = ThresholdHysteresis(5, 30)

    def reset(self, env: SDWanEnv) -> None:
        self.base.reset(env)

    def act(self, env: SDWanEnv) -> int:
        if self.rng.random() < self.epsilon:
            return int(self.rng.integers(env.K**env.C))
        return self.base.act(env)
