# Cross-engine validation scope: model-appropriate recommendation

Status: REVIEW DRAFT for the owner, 18 Nov 2026. Nothing here is adopted.
The original plan (docs/cross_engine_validation_plan.md) and the case
manifest (testbed/scenarios/cross_engine_cases.json) are unchanged and
retained in full; this document adds a scope classification on top of
them. Trigger: the owner confirmed (18 Nov, ~14:27) that no metric in
the current plan is fixed by him or his supervisor, so the plan is
revisable as a matter of research intent. "No compromises" is preserved
as scientific honesty: every metric below stays measured where the
instrument can measure it, and every exclusion is explicit and labelled,
never silent.

## Per-metric classification (grounded in current code)

| metric | class | grounding |
| --- | --- | --- |
| loss_frac | quantity-level comparable | FluidQueue offered/delivered/dropped accounting (env/queue.py) vs runner full-run aggregates (testbed/analyze.py summarize_traffic) |
| throughput_mbps | quantity-level comparable | same accounting both sides; window convention reconciled (full run, no warmup exclusion, matching analyze.py) |
| interruption_s | informative only | emulator value is the calibrated switching model's own output (env/switching.py) fed by testbed measurements; comparing it back is near-circular, so it is reported, never gate evidence |
| delay_median_ms | estimator-level mapping (below) | emulator: per-step aggregate 0.5*RTT + occupancy/service drain (env/sdwan_env.py:243-260); runner: per-packet median over the run |
| jitter_mean_ms | estimator-level mapping (below) | emulator: per-step |delta RTT|*0.5 + 0.2*drain + disruption term (sdwan_env.py:261-270); runner: mean |delta delay| over packets |
| queue_delay_ms | deferred - no adopted estimator | emulator candidate: the same drain estimate (sdwan_env.py:243-249); Mininet candidate: residence-minus-base proxy (analysis/candidates/queue_delay_proxy.py) - UNVALIDATED, 28.0% negatives on the ce01 smoke (n=55,608), causes hypothesized (delay-line/backlog sharing; tap residence includes jitter/OVS/placement; pairing noise), analysis pending |
| reordering_frac | outside the aggregate model class | the fluid model has no packets, hence no packet order; reordering exists only as a calibrated input folded into jitter (sdwan_env.py:270) |

## Recommended scope

1. Gate metrics (quantity-level): loss_frac, throughput_mbps.
   Claims supported: the emulator's aggregate traffic accounting
   (offered/delivered/dropped, capacity enforcement, buffer overflow)
   agrees with the testbed within the adopted bands under matched
   constant inputs.
2. Estimator-level comparisons with defined mappings: delay_median_ms,
   jitter_mean_ms. Bands quantify the observed deviation between two
   different estimators; a pass means agreement within the measured
   band, not equality of the underlying quantities.
3. Informative, reported, never gated: interruption_s.
4. Deferred: queue_delay_ms - enters the gate only after the owner
   adopts an estimator pair and the Mininet candidate's negatives are
   explained; until then both candidates stay flagged.
5. Explicit model-scope boundary: reordering_frac remains a REQUIRED
   Mininet-side diagnostic, measured and reported on every testbed run,
   and the cross-engine gate carries an explicit OUT-OF-MODEL-SCOPE
   entry for it. This is a documented boundary, not a deletion: the
   original requirement stays visible with its provenance. The
   alternative (packet-level emulator core) is a research redesign and
   is not assumed or started here.

## Proposed estimator-level mappings and uncertainty

* delay: emulator median over per-step delay values across the run vs
  runner per-packet median. Under constant-series inputs the emulator
  trace term is flat, so the comparison isolates the drain-estimate
  contribution. Uncertainty: per-step aggregation vs per-packet
  distribution; the fluid drain estimate spreads queue wait uniformly
  over a step while the testbed concentrates it on packets that
  actually queued. The band absorbs this as measured deviation.
* jitter: emulator mean over per-step jitter vs runner mean absolute
  per-packet delay difference. Constant-series mode carries zero trace
  jitter, so case jitter_ms has no emulator-side expression yet; that
  is a recorded harness limitation, and runs with non-zero case jitter
  compare only the queue/disruption contributions.

## What this scope cannot claim

* Anything about packet order, per-packet delay distributions, or
  transport behavior (TCP congestion control, QUIC): the fluid model
  does not carry them.
* That the emulator's delay/jitter equal the testbed's; only that the
  defined estimators agree within measured bands.
* That queue_delay_ms is measured anywhere until the deferred
  definition is adopted.

## The single review decision

Approve or adjust this classification, including the two estimator
mappings in it. Everything else it touches is already delegated or
implemented: band derivation rule (half-range baseline + max-dev
sensitivity), matched-input hooks (constant_series / fixed_load_mbps),
and the fail-closed harness/comparator plumbing.
