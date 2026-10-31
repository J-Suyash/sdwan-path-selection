# Incumbent controllers

Behaviour policies that produce the offline logs:

- Threshold + hysteresis
- Best Quality
- Lowest Cost within SLA

See Section 10.2 of the proposal.

Implementations in `incumbents.py`:

- `ThresholdHysteresis(breach_n, recover_m, scale)` — commercial-style
  rule
- `BestQuality` — lowest-latency link per class
- `LowestCostWithinSla` — cheapest compliant link
- `EpsilonRandom` — threshold base with epsilon-random exploration
  (dataset D3)

All policies share `reset(env)` / `act(env)` and read the environment's
10 s history window to judge link compliance.
