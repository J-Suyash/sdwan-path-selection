# Environment package

Trace-driven Gymnasium emulator of a branch with three underlays
(broadband, 5G, LEO) and four traffic classes (voice, video,
interactive, bulk). See Section 10.1 of the proposal.

## Usage

```bash
PYTHONPATH=. .venv/bin/python scripts/check_emulator.py
```

```python
from env import SDWanConfig, SDWanEnv

env = SDWanEnv(SDWanConfig(), seed=0)
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step(17)  # Discrete(81)
```

- Action: one of 81 joint assignments (3 underlays per class, 4
  classes).
- Observation: 43 features — per-underlay window stats (mean/p95 RTT,
  jitter, loss, capacity, up), per-class state (load, current underlay,
  seconds since switch, recent violations), prices, switch budget
  remaining, time of day.
- Reward: negative cost (scaled micro-dollars). SLA violations and
  switches are reported in `info`, not the reward.
- Traces come from `data/processed/*.parquet`; missing sources fall
  back to a synthetic random-walk series.

## Milestone M1 status

1-hour episode runs in ~0.7 s (~5,000× real time) — meets the M1 speed
target of ≥1,000×.
