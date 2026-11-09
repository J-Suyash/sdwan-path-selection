# Review 0: rubric-aligned brief (2026-11-04)

Rubric: 5 criteria x 2 marks. Feasibility is scored inside criterion 3
("clear, specific, achievable objectives"), not as a separate item.

## 1. Rubric mapping

| Criterion | What earns full marks | Current evidence | Fix before review |
|---|---|---|---|
| Problem identification & formulation | Relevant problem, crisp statement, justification | Slides 3-4: reactive thresholds, flapping, cost blindness; slide 6: online-learning risk | Open with one sentence: "Given only the logs of an incumbent SD-WAN controller, learn a per-class steering policy that lowers cost without breaking SLA or switch budgets, and prove it is no worse before deployment." |
| Literature / market / patents | Relevant sources, market need, patents, explicit gaps | Slides 5, 8, 9, 11; proposal: ~75 papers screened, 13 read in full; Cisco/Juniper patents | Say the screening numbers aloud; name the patents (Cisco 11,159,447 B2; Juniper 11,991,084 B2); cite gap matrix |
| Objectives / product goals | Clear, specific, achievable | Slide 14 epics | Replace with the four staged objectives below; each has a metric and a go/no-go gate |
| SDG alignment | Relevant SDGs and expected contribution | Slide 15: SDG 9 primary, 8, 7/12 | Add one measurable sentence per SDG |
| Presentation & documentation | Clear slides, proper docs, communication | Deck is clean and consistent | Fix the factual items in section 5 |

## 2. Proposed solution: 60-second pitch

"Enterprises now steer traffic across broadband, 5G and LEO satellite
links, but commercial SD-WAN still reacts after users are hurt:
hand-tuned thresholds, no cost awareness, and link flapping. RL can
steer better, but learned agents are not deployable because they
explore on live traffic and offer no evidence they will beat the
controller they replace.

Our solution is a staged, verified pipeline. We anchor on a published
2026 result: Bista et al. show that a neural control-barrier filter
raises multi-class QoS compliance under high load. That gives us a
known, peer-reviewed target. We first reproduce that central effect in
a trace-driven environment. Then we extend it to the enterprise case
the paper does not cover: three underlays, real Starlink/5G/broadband
measurement traces, and discrete per-class path choices. Finally, we
learn from the incumbent controller's logs, verify the policy on
held-out data before deployment, and fine-tune behind a runtime shield
with explicit SLA and switch budgets.

Every stage has a gate. If an extension does not beat its baseline, we
report and analyse the negative result instead of claiming success.
The guaranteed deliverable is a reproduced, benchmarked safety
baseline; each extension is incremental and measurable."

## 3. Objectives rewritten for criterion 3

**O1 (guaranteed). Reproduce the published effect.**
Reimplement Bista 2026's TQC + ensemble + neural-CBF pipeline and
reproduce its qualitative result under high load: the filter improves
joint VoIP-video compliance over the unfiltered agent, with the
expected best-effort trade-off. Target: same direction and ranking,
comparable magnitude (e.g., roughly 63% -> low 70s joint compliance).
Gate: reproduce the ablation ordering; document deviations.

**O2 (target). Extend to three underlays with real traces.**
Port the method to the trace-driven emulator with broadband, 5G and
LEO; discrete per-class decisions. Target: the safety-layer benefit
persists on held-out trace dates. Gate: improvement over the unfiltered
policy without violating the switch budget.

**O3 (target). Learn from incumbent logs with a deployment check.**
Train CQL/IQL on incumbent logs; accept a policy only if off-policy
evaluation beats the incumbent on held-out data within budgets.
Gate: at least one policy accepted, or a documented negative result
with failure analysis.

**O4 (stretch). Shielded fine-tuning, testbed and explanations.**
Runtime shield with SLA/switch budgets; Mininet cross-check; decision
tree + SHAP; open benchmark release. Gate: testbed confirms the
ranking; tree fidelity >= 90% with <5% cost loss.

## 4. SDG one-liners

- **SDG 9 (primary):** software that makes non-fibre links (5G, LEO)
  usable for remote branches, improving resilience of existing
  infrastructure without new fibre (targets 9.1, 9.c, 9.4).
- **SDG 8:** fewer dropped calls and lower WAN cost per GB for SMEs
  and distributed enterprises (8.2).
- **SDG 7 / 12:** less over-provisioning and unnecessary switching,
  reducing bandwidth and network energy (7.3, 12.2).

## 5. Documentation fixes before submission

1. **Wrong PDF:** `Docs/Base Paper.pdf` is Botta et al. 2024, not
   Bista 2026. Present the actual 2026 paper (DOI
   10.23919/IFIPNetworking70592.2026.11579208; HAL hal-05677079).
2. **Do not claim public code.** The paper's cited repo
   `github.com/safeml/sdwanQoS` returns 404; the lab's `safeml/sdwan`
   repo has no CBF/TQC files in any branch. Say: "method is
   reimplemented from the paper; artifacts are not publicly available."
3. **Soften "first" claims** to "to our knowledge" or "we aim to",
   unless the survey supports them.
4. Remove "OmniSafe" from the *working tools* list (deferred due to
   dependency conflicts); keep it as a planned alternative.

## 6. Likely questions and answers

**Is the 2026 paper reproducible?**
"The method is reimplementable because the paper specifies the
architecture, hyperparameters and protocol. The artifacts are not
publicly available: the cited code link is 404 and the lab repo has no
safety code. So our target is qualitative reproduction with comparable
magnitudes, not bit-exact numbers."

**Why not just run their code?**
"It is not available. We verified this, so the plan budgets for
reimplementation and documents any deviations."

**What if offline RL does not beat the threshold controller?**
"That is a planned outcome, contribution C4: analysing when and why
offline RL fails. Reproduction still delivers a validated benchmark
and safety baseline."

**Is this novel?**
"The underlying safety method is not ours and we will not claim it.
The contribution is the deployment-verified extension: three real
underlays, discrete per-class decisions, incumbent-log learning and
budgeted safety."

**Why three links?**
"Broadband, 5G and LEO have complementary cost/latency behaviour, and
multi-path adaptation is explicitly left as future work in the base
paper."

**How will you know it worked?**
"Cost per GB, per-class SLA-violation rate against budgets, switches
per minute, and joint compliance, compared with strong incumbents and
published baselines, with held-out dates and multiple seeds."
