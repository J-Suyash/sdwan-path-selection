# Environment documentation

## Machine

- Host: Linux (team laptop)
- Mininet and Open vSwitch installed
- Python managed with `uv`; project pinned to Python 3.11

## Phase 0 checks

- [x] Python 3.11.15 environment with PyTorch 2.15.0+cpu, Gymnasium,
      d3rlpy 2.8, Stable-Baselines3, sb3-contrib
- [x] Mininet `pingall` works (`sudo mn --switch ovs --test pingall`,
      0% dropped, verified 2026-10-31)
- [x] d3rlpy CQL example runs on CartPole (scripts/check_cql_cartpole.py,
      final mean return ~321)
- [x] os-ken installed in the environment (testbed controller)
- [ ] OmniSafe — deferred, see note below

## Notes

System Python is 3.14; do not use it directly for the RL stack. Always
activate the uv-managed 3.11 environment.

Mininet and its Open vSwitch bindings are installed only for system Python.
Use `.venv/bin/python` for emulator, analysis and dry-run tooling, and
`sudo env PYTHONPATH="$PWD" /usr/bin/python3 -m ...` for the Mininet
testbed. The project virtual environment cannot import Mininet.

OmniSafe currently forces `pandas==2.0.3` and `pillow==11.3.0`
downgrades (its pins predate NumPy 2 / pandas 3). Decision: install it
in Phase 2 only when the Lagrangian-PPO baseline is needed, or use the
custom-PyTorch fallback from Section 12 of the proposal.

d3rlpy's bundled `get_cartpole()` environment is legacy gym 0.26 and
breaks under NumPy 2; evaluate with a Gymnasium env instead (see
scripts/check_cql_cartpole.py).

## Delay semantics (fixed 2026-11-10)

Every trace delay input is a **round-trip** ping measurement: WetLinks
`ping_avg` (ICMP echo), Raca5G `PINGAVG` (Android ping), LENS ping/iperf
`rtt` (the repo also distributes IRTT one-way metrics; any future LENS
field must be pinned per field before use), the collected `vps2vps`,
`home_broadband` and 5G-hotspot ping logs, and RIPE Atlas ping results.
Lumos5G has no RTT field at all (NaN in the unified schema). The SLA
delay thresholds (voice 150 ms, video 150 ms, interactive 200 ms),
following ITU-T G.114 and the proposal, are **one-way**. The emulator
therefore maps one-way delay = round-trip / 2
(`SDWanConfig.oneway_delay_factor = 0.5`), under a symmetric-path
assumption, and applies the same mapping to the trace-jitter component
and to the incumbent `link_ok` test; queueing delay is already one-way.

Consequences to treat as empirical, not cosmetic:

- A broadband leg whose RTT historically exceeded 150 ms used to breach
  the voice delay SLA every second; it is now delay-compliant when its
  one-way equivalent is under threshold, so **safety classifications of
  assignments can flip**, not just violation magnitudes.
- `scripts/reassess_delay_semantics.py` records post-fix incumbent
  rankings in `analysis/baseline_results.csv` (rows prefixed
  `rttfix_`). Relative ranking of incumbents is unchanged
  (threshold-hysteresis safest, best-quality most expensive,
  lowest-cost cheapest with violations, random worst), but absolute
  violation counts are driven now by outage windows and loss/jitter,
  and per-seed variance is large (1 to 952 voice violations/h across
  3 seeds on `medium`).
- Path asymmetry is unmeasured; if Mininet cross-engine calibration
  shows systematic asymmetry, revisit the factor per underlay.

## Infrastructure (VPS)

- `alc` — Ubuntu 24.04, 2 cores / 7.8 GiB, public IP 94.103.167.15
  (answers ICMP publicly), Tailscale 100.76.255.20, ~23 GB disk free.
  SSH: `sxtr@alc` with default key. No longer runs a collector; only
  serves as the ping target.
- `bigguy` — Ubuntu 24.04, 2 cores / 11 GiB, public IP 144.24.130.58
  (Oracle Cloud; internet only reaches port 22 — ICMP and 5201 are
  filtered by the VCN). Tailscale 100.113.191.84. SSH: key
  `~/.ssh/bigguy`, `ubuntu@144.24.130.58`. iperf3 server runs as a
  systemd service on port 5201, reachable over Tailscale. Tailscale
  SSH is disabled (`tailscale set --ssh=false`), so `ubuntu@bigguy`
  and the public IP both reach normal sshd. ~73 GB disk free, so it is
  the collector host: runs the vps2vps collector (ping every 200 ms to
  alc's public IP, CSV at ~/sdwan-collect/traces_vps2vps.csv) plus the
  iperf3 server.
- Home laptop collector (this machine): pings alc's public IP every
  200 ms, iperf3 every 10 min to bigguy over the direct Tailscale
  path. CSV: data/raw/collected/home_broadband.csv. Stop with
  `pkill -f collect_traces.py`.
- Tailscale links between peers are direct (no relay), so trace
  latency and throughput reflect the real public path between them.
