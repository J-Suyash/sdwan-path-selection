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

OmniSafe currently forces `pandas==2.0.3` and `pillow==11.3.0`
downgrades (its pins predate NumPy 2 / pandas 3). Decision: install it
in Phase 2 only when the Lagrangian-PPO baseline is needed, or use the
custom-PyTorch fallback from Section 12 of the proposal.

d3rlpy's bundled `get_cartpole()` environment is legacy gym 0.26 and
breaks under NumPy 2; evaluate with a Gymnasium env instead (see
scripts/check_cql_cartpole.py).

## Infrastructure (VPS)

- `alc` — Ubuntu 24.04, 2 cores / 7.8 GiB, public IP 94.103.167.15
  (answers ICMP publicly), Tailscale 100.76.255.20. SSH: `sxtr@alc`
  with default key. Runs the vps2vps collector (ping every 200 ms to
  bigguy, CSV at ~/sdwan-collect/traces_vps2vps.csv).
- `bigguy` — Ubuntu 24.04, 2 cores / 11 GiB, public IP 144.24.130.58
  (Oracle Cloud; internet only reaches port 22 — ICMP and 5201 are
  filtered by the VCN). Tailscale 100.113.191.84. SSH: key
  `~/.ssh/bigguy`, `ubuntu@144.24.130.58`. iperf3 server runs as a
  systemd service on port 5201, reachable over Tailscale. Tailscale
  SSH is disabled (`tailscale set --ssh=false`), so `ubuntu@bigguy`
  and the public IP both reach normal sshd.
- Home laptop collector (this machine): pings alc's public IP every
  200 ms, iperf3 every 10 min to bigguy over the direct Tailscale
  path. CSV: data/raw/collected/home_broadband.csv. Stop with
  `pkill -f collect_traces.py`.
- Tailscale links between peers are direct (no relay), so trace
  latency and throughput reflect the real public path between them.
