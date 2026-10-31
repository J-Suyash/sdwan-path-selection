# AI-Driven SD-WAN Path Selection for Enterprise

**Learning from the Incumbent: Offline-to-Online Safe Reinforcement
Learning for Traffic Steering in Broadband--5G--LEO Enterprise SD-WANs**

Major project repository. Full proposal:
[`Docs/AI-Driven SD-WAN Path Selection – Detailed Proposal and Plan.docx`](Docs/AI-Driven SD-WAN Path Selection – Detailed Proposal and Plan.docx)

## What this project does

Learn a per-application path-selection policy over broadband, 5G and LEO
links from the logs of an existing threshold-based SD-WAN controller,
verify it offline before deployment, then fine-tune it online behind a
runtime safety shield, under explicit budgets on SLA violations and path
switches, while minimizing link cost.

## Repository layout

- `data/` — public and team-collected traces, offline datasets (D1--D3)
- `env/` — trace-driven Gymnasium emulator of a three-underlay branch
- `policies/` — incumbent controllers (threshold+hysteresis, best
  quality, lowest cost within SLA)
- `offline/` — CQL/IQL learning, constraint critics, off-policy
  evaluation and the deployment acceptance test
- `online/` — shielded online fine-tuning (Lagrangian budgets + runtime
  shield)
- `testbed/` — Mininet + Open vSwitch + os-ken/Ryu testbed
- `analysis/` — experiment runner, statistics, figures
- `paper/` — manuscript and notes
- `configs/` — Hydra configuration files
- `docs/` — environment and methodology documentation
- `scripts/` — trace collection and preprocessing scripts

## Setup

Python 3.11 is pinned for compatibility with the RL stack:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt
```

OmniSafe is intentionally deferred: it currently forces a pandas
downgrade. Install it only when Phase 2 Lagrangian baselines need it, or
use the custom-PyTorch fallback from Section 12 of the proposal.

## Roadmap

Six phases over ~24 weeks (November 2026 -- April 2027). See Section 14
of the proposal for the full execution plan.
