# Environment documentation

## Machine

- Host: Linux (team laptop)
- Mininet and Open vSwitch installed
- Python managed with `uv`; project pinned to Python 3.11

## Phase 0 checks

- [x] Python 3.11.15 environment with PyTorch 2.15.0+cpu, Gymnasium,
      d3rlpy 2.8, Stable-Baselines3, sb3-contrib
- [ ] Mininet `pingall` works (needs root; passwordless sudo not set up)
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
