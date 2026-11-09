# Environment package

Trace-driven Gymnasium emulator of a branch with three underlays
(broadband, 5G, LEO) and four traffic classes (voice, video,
interactive, bulk). The active workload is an explicit branch ->
user/device -> session -> flow hierarchy; see `docs/workload_model_spec.md`.

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
- Reward: negative delivered-traffic cost (scaled micro-dollars). Offered,
  admitted, delivered and dropped traffic are reported separately in `info`.
  SLA violations and switches are also reported there.
- Traces come from `data/processed/*.parquet`; missing sources fall
  back to a synthetic random-walk series.

The emulator uses a bounded `fifo-fluid` queue and labels its transport
approximation as `fluid-rate-v1`. It does not claim to implement TCP CUBIC,
BBR, packet scheduling or kernel retransmissions. Switching effects remain
zero until measured calibration rows are supplied; this state is exposed as
`info["switching_calibrated"]`.

`episode_seconds` is simulation time. The number of calls to `step()` is
`episode_seconds / decision_interval_s`; it is validated to be integral.
`info["lifecycle"]` reports session and flow totals with censoring separated
from natural completion.

## Milestone M1 status

1-hour episode runs in ~0.7 s (~5,000× real time) — meets the M1 speed
target of ≥1,000×.
