# Workload Model Specification

## Scope and provenance

The generator creates a calibrated hybrid workload for experiments. Public
datasets contribute link or application-specific distributions only; records
from unrelated datasets are not concatenated into an enterprise trace. Values
in the default profiles are assumptions until the parameter registry marks a
field as measured or literature-derived.

An initial controlled application-flow extraction covers VoIP, Google Meet,
Gmail and Dropbox from SDNCampus v1. Its method and limits are recorded in
`analysis/application_profile_summary.md`. It supports flow rate and timing
cross-checks only; population, session arrivals, session durations and
concurrency remain explicit assumptions.

## Hierarchy and lifecycle

1. A `BranchProfile` defines a scenario population, operating window,
   activity fraction, regime multiplier and application mix. Experiments may
   force `low`, `normal`, `peak` or `stress`; otherwise the profile derives a
   time-of-day regime.
2. `UserDevice` identities are created for the profile and selected as active
   users per time step.
3. An `ApplicationSession` has its own start/end, class, user/device owner and
   attributes. Session duration is independent of flow duration.
4. Each session creates one or more related `Flow` objects. Flows carry a
   direction, transport, rate, session ID and optional `response_to` link.
5. The generator retains concurrent sessions and flows. Natural termination
   and simulation-boundary censoring are recorded separately. `advance()` marks
   only natural completion; `finalize(episode_end_s)` records uncensored
   completion on or before the horizon and censors unfinished sessions and
   flows at that horizon.

`WorkloadSnapshot` is the emulator-facing fluid abstraction: offered Mbps and
bytes by class, active users/sessions/flows and lifecycle counts. The object
does not claim to generate packet headers or kernel transport behavior.
`info["lifecycle"]` exposes cumulative session and flow totals so censored
objects are never reported as completed observations.

## Application behavior

- Voice is bidirectional UDP media in the fast model. Codec, packetization and
  silence suppression remain calibration parameters.
- Video is bidirectional UDP media with a variable-rate approximation. It is
  not labelled as a specific conferencing product profile.
- Interactive traffic has a TCP request flow and related response flow;
  connection reuse and think-time distributions are pending extraction.
- Bulk traffic is a finite-size TCP transfer approximation. Mininet uses a
  closed-loop kernel TCP transfer and is the calibration reference.

## Emulator queue and transport boundary

At each decision step, `env/queue.py` processes offered arrivals and service
capacity. It drains existing backlog first, admits new arrivals into the
remaining buffer, reports overflow drops once, and keeps
`0 <= occupancy <= buffer`. Per-class delivery/drop values are proportional
shares of the underlay aggregate in the fluid model. The queue discipline is
`fifo-fluid`; packet scheduling and retransmission are not simulated.

`episode_seconds` is wall-clock simulation duration, not a step count.
`episode_steps = episode_seconds / decision_interval_s`; configuration rejects
non-integral divisions. Trace windows, history lengths and minute switch
budgets are derived from the same time base.

Trace capacity may be zero. The environment then reports no service and any
new traffic beyond the bounded buffer is dropped. Offered, admitted,
delivered and dropped traffic are distinct metrics in `info["queue"]`.

## Switching calibration contract

`env/switching.py` selects a nearest measured observation by old/new RTT and
jitter, packets in flight, flow type, transport and queue occupancy. The
required columns are in `data/switching_calibration_template.csv`. Until
controlled Mininet measurements populate that file, switching effects are
zero and `info["switching_calibrated"]` is false. This is an explicit
uncertainty state, not a safety guarantee.

## Reproducibility and validation

Record profile, random seed, underlay trace segment, simulator version and
policy version in every generated transition. Use independent time/session
aware holdouts; do not share trace windows or workload seeds across splits.
Compare flow/session counts, rates, durations, burstiness and tails with
bootstrap intervals. Set acceptance thresholds only after measuring natural
variation and testbed repeatability.
