# Reproducibility check: Bista et al., IFIP Networking 2026

**Paper:** Safety-Aware Multi-Class QoS Control in SD-WAN via
Ensemble-Based Neural CBFs. G. Bista, K. Singh, A. Pegatoquet,
E. Moulay. IFIP Networking 2026.
DOI: 10.23919/IFIPNetworking70592.2026.11579208.
Open-access copy: https://hal.science/hal-05677079 (CC BY-NC-ND 4.0).

Checked on 2026-11-03.

## Verdict

**Reimplementable from the paper; not artifact-reproducible as claimed.**

- Qualitative reproduction (same direction and ranking of effects) is
  feasible for a competent team.
- Exact-number reproduction is unlikely without the authors' code and
  missing setup details.
- "Run their code and get their tables" is **not** currently possible.

## Artifact evidence

1. The paper's footnote states: "Code and simulation artifacts:
   https://github.com/safeml/sdwanQoS". This repository returns
   **HTTP 404** (GitHub API also 404) as of 2026-11-03. It is either
   private or does not exist.
2. The lab org `safeml` has three public repos: `sdwan`,
   `safeml.github.io`, `csma`. `safeml/sdwan` has branches main (44
   files), dev (95 files), dev-dockerize (39 files); **no file in any
   branch mentions CBF, TQC, safety or ensemble**.
3. `safeml/sdwan`'s README cites a different paper (KAN-PPO, CCNC
   2026) and contains PPO/KAN/DDPG/TD3 code, not the safety filter.
4. No dataset, transition buffer, trained model or config bundle for
   the 2026 paper is published.

## What the paper does specify well

- ns-3 3.39 + ns3-gym + OpenFlow 1.3; two sites, Internet and MPLS.
- Link ranges: Internet 10-50 Mb/s / 15-40 ms; MPLS 5-30 Mb/s /
  8-25 ms; per-class priority queueing.
- Traffic: VoIP 64 kb/s CBR; video 1 Mb/s; BE 2 Mb/s; 1 s decisions.
- State: 35-dim; action: 3 continuous split ratios in [-1, 1].
- TQC: 2x256 actor, quantile critics, 25 quantiles, drop top 5;
  lr 3e-4, tau 0.005, gamma 0.99, grad clip 1.0.
- Ensemble: 5 members, 3x256, lr 1e-3; adaptive kappa 0.15/0.3.
- CBF projection: 2 passes, 11 candidates, radius 0.35 with 0.6
  decay, 3.2 ms margin; lexicographic VoIP then video.
- Training: 800 episodes x 100 steps; evaluation 20 episodes x 50
  steps; ns-3 seeds 0-49 train, 50-69 inference.
- Results and ablations are tabulated (Tables III-V).

## What is missing or inconsistent

- The ensemble training-set size is stated as 20,000 transitions in
  Section III-B and 80,000 in Section IV.
- No exact queue sizes, scheduler parameters, cross-traffic model or
  episode-reset protocol.
- Ensemble input/output feature definitions are not fully specified.
- The "Baseline [31]" reimplementation details are absent.
- No random seeds for network/traffic generation beyond ns-3 seed
  ranges; no confidence intervals across seeds.
- Paper explicitly disclaims formal invariance under model error.

## Implications for the major project

- Treat reproduction as a **reimplementation from the paper**, with
  qualitative and approximate quantitative targets (e.g., CBF raises
  high-load joint compliance from roughly 63% toward the low 70s,
  with the BE trade-off), documented against Tables III-V.
- Do not claim "public code available" in Review 0.
- If a different anchor paper is desired, Bista's own lineage is
  Dinh et al. (Computer Communications 2025, baseline [31]) and Dinh
  et al. (NOMS 2024, CBF + DRL); those artifacts must be verified
  separately before committing.
