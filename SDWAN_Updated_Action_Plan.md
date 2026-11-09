# SD-WAN Major Project --- Updated Action Plan for the Existing Project Agent

**Purpose:** Update the existing agent's working assumptions, task list
and recommendations. This is the current planning baseline. Dataset
contents, numerical parameters and implementation choices remain subject
to verification.

## 1. Updated project direction

The project scope is unchanged:

-   Underlays: broadband, 5G and LEO satellite.
-   Application classes: voice, video, interactive/SaaS and bulk.
-   Offline RL: CQL and IQL trained separately; behaviour cloning as an
    imitation baseline.
-   Offline policy evaluation: FQE and WIS, with uncertainty and
    action-support analysis.
-   Runtime: safety shield and fallback to the existing threshold-based
    controller.
-   Validation: fast Gymnasium emulator plus packet-level Mininet/OVS
    testbed.
-   Underlay inputs: the project's existing measured link traces.

**Adopt a calibrated hybrid hierarchical workload generator.** Use
public datasets in distinct, evidence-supported roles. Do not
concatenate raw records from unrelated datasets and call the result an
enterprise trace.

The hierarchy is:

**Branch profile → users/devices → application sessions → flows →
packet/transport behaviour.**

The Gymnasium environment uses a fast flow/fluid-queue abstraction for
large-scale RL. Mininet/OVS uses real packets and kernel transport for
selected validation experiments. Compare both under matched scenarios.

## 2. Corrections to the previous research report

The previous report is a conceptual proposal, not an implementation
specification.

### Dataset claims need an audit

-   Verify original publications and repositories before relying on
    metadata.
-   Inspect actual downloadable files, schemas, sample records,
    timestamp semantics, capture duration and licensing.
-   Do not infer fields from a paper summary or secondary source.
-   Do not treat aggregate time series as flow-level data.
-   Do not describe campus, ISP, residential or security-testbed traffic
    as representative enterprise traffic without qualification.
-   Do not claim a newer dataset version exists without a verifiable
    repository release.
-   Resolve conflicting DOI/repository links.
-   Record repository version, retrieval date, filenames, file sizes and
    licence.

### Numerical parameters are not approved

The previous report gives specific values for user population, session
rates, durations, Pareto parameters, packet rates, bitrates, think times
and traffic ratios. Treat all as **unverified hypotheses** until traced
to actual data or primary sources.

For every parameter, record: - Parameter and unit. - Application
class. - Source dataset/file/field, primary paper, testbed measurement
or explicit assumption. - Extraction method and sample size. -
Uncertainty or confidence interval. - Where it is used in the model. -
Status: verified, provisional, assumed or unavailable.

Do not label a parameter empirical merely because a dataset has a
vaguely related application label.

### The generator must implement a real hierarchy

The previous Python sketch selects an application class and emits a
flow. It does not implement the claimed hierarchy.

The implementation must explicitly represent: - Branch/workload
profile. - User/device identity and activity. - Application session with
start/end and session-level attributes. - One or more related flows per
session. - Packet/byte generation or a documented transport
abstraction. - Directionality and request/response relationships where
applicable. - Concurrent sessions and flows. - Session and flow
termination/censoring. - Application-specific response to congestion.

Do not claim the hierarchy is implemented until these relationships
exist in the data structures and generator logic.

### Queue, loss and transport models need correction

Do not copy the previous queue equations or fixed TCP loss response
directly into production code.

The queue model must: - Keep occupancy bounded: (0 `\leq `{=tex}Q(t)
`\leq `{=tex}B). - Account for arrivals, service/drain and overflow
drops. - Use consistent time units. - Handle capacity variation and
zero/near-zero capacity. - Distinguish offered load, admitted traffic,
delivered throughput and dropped traffic. - Specify queue discipline,
scheduling and buffer sharing. - Avoid double-counting overflow.

A starting discrete accounting structure is:

\[ A_t = `\sum`{=tex}\_f r_f(t)`\Delta `{=tex}t \]

\[ Q\_{t+1} =
`\min`{=tex}(B,`\max`{=tex}(0,Q_t+A_t-C_t`\Delta `{=tex}t)) \]

The implementation must separately calculate overflow drops from
arrivals exceeding available buffer space. This equation alone is not a
complete packet scheduling model.

Do not call a fixed multiplicative rate reduction "TCP CUBIC" or "BBR".
If Gymnasium uses a simplified transport approximation, label it as such
and calibrate it against Linux TCP behaviour in Mininet. Use actual
kernel TCP in the packet-level testbed.

### Path-switching penalties must be measured

Remove the unsupported formula mapping RTT difference directly to a
switching packet-loss probability.

Measure switching under controlled combinations of: - Old/new path RTT,
jitter and delay difference. - Packets in flight. - Flow type and
transport protocol. - Flow-rule update method and installation time. -
Connection/transport state handling. - Queue occupancy and congestion on
both paths.

Measure interruption duration, packet loss, reordering, retransmissions
and application QoS. Build an emulator switching model from those
measurements and report uncertainty.

### Validation thresholds must not be arbitrary

Do not adopt the previous suggested values (for example NRMSE ≤ 0.08,
Wasserstein distance ≤ 0.05, MAPE ≤ 7.5%, correlation ≥ 0.94) as
established requirements.

Establish thresholds using: - Time- and session-aware train/holdout
splits. - Natural variation between independent real-data subsets. -
Bootstrap uncertainty. - Measurement noise and testbed repeatability. -
Intended model use and downstream QoS sensitivity.

A KS-test p-value above 0.05 does not prove equivalence. Use
distribution plots, tail comparisons, suitable distance/effect measures
and uncertainty intervals.

## 3. Dataset strategy and audit

These are candidate roles, not final approvals.

  ----------------------------------------------------------------------------
  Dataset                 Provisional role        Limitation / action
  ----------------------- ----------------------- ----------------------------
  CESNET-TimeSeries24     Aggregate institutional Coarse aggregates; cannot
                          demand and temporal     reconstruct individual
                          variation               packets. Verify schema, time
                                                  bins and files.

  SDNCampus               Application-specific    Controlled
                          flow characteristics    application-by-application
                                                  captures; does not establish
                                                  natural mixed-application
                                                  concurrency. Verify version
                                                  and fields.

  DARPA SEARCHLIGHT       Packet-level behaviour  Scripted testbed workflows,
                          for selected            not organic office traffic.
                          interactive,            Verify accessible phases and
                          conferencing and video  metadata.
                          workflows               

  CESNET-QUIC22           QUIC flow and packet    Backbone/campus context, not
                          metadata                an enterprise branch. Verify
                          characteristics         fields and trace
                                                  availability.

  CTU-SME-11              SME-like                Security-oriented dataset
                          device/background       with malicious activity;
                          activity and connection filter unsuitable scenarios
                          patterns                before fitting benign
                                                  workload parameters.

  Real Network            Access-network flow     ISP/residential access
  Environment (2025)      characteristics and     context, not enterprise
                          comparison              branch traffic. Resolve
                                                  paper/repository DOI and
                                                  inspect files.
  ----------------------------------------------------------------------------

### Dataset audit checklist

-   [ ] Create a register: paper URL, repository URL, DOI, version,
    publication date, collection period, licence and access
    requirements.
-   [ ] Inspect repository metadata and downloadable archives.
-   [ ] List actual files, sizes, formats and archive structure.
-   [ ] Inspect representative records and build a schema inventory.
-   [ ] Verify timestamp units, timezone, resolution, capture duration
    and clock consistency.
-   [ ] Determine unidirectional/bidirectional semantics, flow keys,
    active/inactive timeouts and termination rules.
-   [ ] Identify application labels and how they were assigned.
-   [ ] Check encryption, truncation, anonymisation and sampling.
-   [ ] Determine whether traffic is concurrent, isolated, scripted,
    passive or actively generated.
-   [ ] Check licence and redistribution restrictions.
-   [ ] Classify each candidate: keep, conditional, reference-only or
    reject, with evidence.

**Deliverables:** `dataset_audit.md` and `dataset_manifest.csv` or JSON.

## 4. Workload model design

### Define the target branch profile first

Do not hard-code 50 users or another population without defining the
scenario. Create configurable small, medium and larger branch profiles,
and identify one primary evaluation profile. These are experimental
profiles, not claims about all enterprises.

-   [ ] Define employee/device population, operating hours, application
    mix and expected concurrency.
-   [ ] Separate total users, active users and concurrent sessions.
-   [ ] Define low, normal, peak and stress regimes.
-   [ ] Mark every value as measured, literature-derived or assumed.

### Implement the hierarchy

-   [ ] Branch profile produces time-varying active-user/device
    populations.
-   [ ] User/device activity produces application-session arrivals.
-   [ ] Sessions create related flows according to application
    structure.
-   [ ] Flows produce packet/byte traffic or use a documented transport
    abstraction.
-   [ ] Track session and flow lifetimes independently.
-   [ ] Preserve correlations where evidence supports them.
-   [ ] Record random seeds and parameter configurations.

### Application-specific modelling

**Voice** - Model bidirectional media and relevant signalling/control at
the chosen scope. - Define codec/frame interval, packetization, bitrate
variation, duration and silence-suppression assumptions. - Treat media
as generally non-responsive UDP unless the selected implementation
demonstrates otherwise. - Validate cadence and directional rates against
captures or controlled generators.

**Video** - Distinguish interactive conferencing from one-way streaming
if both are included in the video class. - Model variable
bitrate/adaptation only with an explicit, defensible mechanism. - Do not
present a generic fixed bitrate rule as a measured Zoom/WebRTC
profile. - Validate rate changes, burst structure, directionality and
response to delay/loss.

**Interactive/SaaS** - Model request/response transactions, connection
reuse, bursts and user think time. - Distinguish application-session
duration from individual transaction/flow duration. - Do not equate a
flow record with a user session.

**Bulk** - Model finite transfer sizes and concurrent transfers. - Use
closed-loop TCP in Mininet. - In Gymnasium, use a documented transport
approximation calibrated against testbed throughput and completion
time. - Measure effects on competing latency-sensitive classes.

### Correlations and non-stationarity

-   [ ] Model time-of-day variation without assuming one universal
    enterprise daily curve.
-   [ ] Preserve session-to-flow relationships.
-   [ ] Preserve request/response directionality where measurable.
-   [ ] Test burstiness and temporal correlation at multiple timescales.
-   [ ] Model concurrency rather than independently sampling every flow.
-   [ ] Separate open-loop sources (e.g. fixed-rate media) from
    closed-loop sources (e.g. TCP/adaptive applications).
-   [ ] Do not assert a universal Hurst parameter or heavy-tail
    exponent; estimate from relevant traces and report uncertainty.
-   [ ] Include multiple workload profiles and stress regimes.

**Deliverables:** `workload_model_spec.md`, parameter registry,
generator API/schema and reproducible configuration files.

## 5. Emulator and testbed coupling

### Gymnasium emulator

-   [ ] Define time-step duration and align it with underlay telemetry.
-   [ ] Define event aggregation within each step.
-   [ ] Define per-underlay capacity, propagation delay, jitter and loss
    from measured traces.
-   [ ] Define queue discipline, capacity, scheduling and drop policy.
-   [ ] Define per-class/per-flow allocation and shared bottleneck
    contention.
-   [ ] Distinguish offered load, delivered throughput and dropped
    traffic.
-   [ ] Label transport approximations and limitations.
-   [ ] Implement application-specific congestion response only where
    justified.
-   [ ] Define switching state and calibrated transient effects.
-   [ ] Unit-test byte conservation, queue bounds, capacity limits and
    deterministic replay.

### Mininet/OVS testbed

-   [ ] Build a reproducible branch/hub topology and three logical
    underlays.
-   [ ] Use OVS and the chosen controller interface for path steering.
-   [ ] Use `tc-netem` for delay, jitter and loss; use a rate limiter
    such as TBF for capacity.
-   [ ] Drive impairments from measured underlay traces with documented
    time alignment.
-   [ ] Generate actual UDP media-like traffic and TCP/QUIC traffic as
    appropriate.
-   [ ] Record PCAPs, flow counters, queue statistics, retransmissions
    and application throughput.
-   [ ] Measure path-switching interruption, reordering and loss.
-   [ ] Repeat experiments with fixed configurations/seeds where
    applicable.

### Cross-engine validation

-   [ ] Define matched scenarios executable in both engines.
-   [ ] Match workload, underlay trace segment, queue configuration and
    path actions.
-   [ ] Compare per-class throughput, delay, jitter, loss, queue
    occupancy and flow completion time.
-   [ ] Compare transients during congestion and switching, not only
    steady-state averages.
-   [ ] Report error distributions and confidence intervals across
    repeated runs.
-   [ ] Set acceptance thresholds after measuring testbed repeatability
    and empirical variability.

**Deliverable:** emulator/testbed comparison report with reproducible
scenarios and plots.

## 6. Offline RL dataset quality and safety

The offline dataset is generated by running baseline controllers against
the validated workload/network environment. It is not a collection of
public PCAP records.

Use a versioned transition schema such as:

\[ (s_t,a_t,r_t,c_t,s\_{t+1},`\text{metadata}`{=tex}) \]

Metadata should include workload profile, random seed, underlay-trace
segment, baseline-policy version and simulator version.

-   [ ] Log state, action, reward/cost, constraint vector, next state
    and episode termination.
-   [ ] Record behaviour-policy identity and action probabilities where
    available; WIS requires valid behaviour-policy probabilities.
-   [ ] Check coverage for the 81-action joint action space.
-   [ ] Measure state-action support by workload regime and underlay
    condition.
-   [ ] Ensure baseline data includes congestion and link-degradation
    conditions.
-   [ ] Keep train/validation/test workload seeds and profiles separate.
-   [ ] Prevent leakage of identical trace windows or workload seeds
    across splits.
-   [ ] Train CQL and IQL separately on comparable datasets.
-   [ ] Keep behaviour cloning as a distinct imitation baseline.
-   [ ] Validate FQE/WIS estimators in the emulator where true policy
    returns can be measured.
-   [ ] Report WIS effective sample size and weight degeneracy.
-   [ ] Treat bootstrap intervals as uncertainty estimates, not safety
    guarantees.
-   [ ] Keep Lagrangian average-constraint optimisation distinct from
    the runtime safety shield.
-   [ ] Stress-test on workload distributions not used for training.

### Generalisation experiments

-   [ ] Unseen combinations of application demand and underlay
    conditions.
-   [ ] Peak concurrent video plus bulk transfer.
-   [ ] Sudden broadband capacity reduction.
-   [ ] 5G degradation and burst loss.
-   [ ] LEO latency/jitter/handover events grounded in measured traces.
-   [ ] Different branch populations and application mixes.
-   [ ] Flow-size/session-duration parameters varied within
    evidence-supported uncertainty ranges.
-   [ ] Ablation with and without workload randomisation.
-   [ ] Compare performance and SLA risk across independent workload
    seeds.

Do not claim robust generalisation from one hand-picked stress scenario.

## 7. Ordered execution plan and gates

Do not begin full RL training until earlier gates pass.

  -----------------------------------------------------------------------
  Phase                   Actions                 Exit condition
  ----------------------- ----------------------- -----------------------
  0\. Correct plan        Update agent            Updated plan and issue
                          assumptions; downgrade  register
                          unsupported values and  
                          equations               

  1\. Dataset audit       Inspect repositories,   Dataset audit and role
                          files, schemas,         classification
                          timestamps and licences 

  2\. Empirical           Extract supported       Scripts, parameter
  extraction              distributions and       registry and plots
                          uncertainty             

  3\. Workload            Define branch profiles  Reviewed specification
  specification           and session/flow        and generator schema
                          hierarchy               

  4\. Generator           Implement concurrent    Deterministic generator
  implementation          sessions, related flows with unit tests
                          and application         
                          behaviour               

  5\. Workload validation Compare flow and        Validation report with
                          aggregate statistics    uncertainty
                          with held-out data      

  6\. Emulator            Couple workload with    Stable Gymnasium
  integration             measured underlays,     environment and
                          queues and switching    invariant tests

  7\. Mininet/OVS         Run matched             Cross-engine
  validation              packet-level and        calibration report
                          switching experiments   

  8\. Baseline logging    Run baseline policies   Versioned datasets with
                          and log transitions     coverage audit

  9\. Offline RL/OPE      Train CQL/IQL/BC and    Reproducible policy and
                          evaluate FQE/WIS        evaluation results

  10\. Shielded online    Test policy with        Safety and stress-test
  test                    runtime shield and      report
                          fallback                
  -----------------------------------------------------------------------

**Gate rule:** If a phase fails its evidence or validation requirements,
correct the model or narrow the claim before proceeding. Do not conceal
failed validation with a newly invented threshold.

## 8. Immediate next actions for the existing agent

Execute in this order:

1.  [ ] Read the detailed proposal and Review 0 documents.
2.  [ ] Treat this file as the current workload-modelling direction.
3.  [ ] Create an issue register separating verified facts, unresolved
    questions, assumptions and rejected claims.
4.  [ ] Audit CESNET-TimeSeries24, SDNCampus, SEARCHLIGHT,
    CESNET-QUIC22, CTU-SME-11 and the 2025 Real Network Environment
    dataset against original repositories.
5.  [ ] Correct repository identifiers, version claims, file-size claims
    and schema descriptions.
6.  [ ] Recommend dataset roles based on inspected files, not secondary
    summaries.
7.  [ ] Build the parameter registry; leave values unavailable where
    evidence is missing.
8.  [ ] Rewrite the generator specification as a real branch →
    user/device → session → flow hierarchy.
9.  [ ] Review queue, transport and switching models before
    implementation.
10. [ ] Propose the minimum controlled Mininet experiments needed to
    calibrate the emulator.
11. [ ] Return a dependency-aware backlog with effort, risks and
    deliverables.
12. [ ] Do not generate large RL transition datasets until workload and
    emulator validation gates pass.

## 9. Rules for the project agent

1.  Evidence before numbers: every empirical parameter must point to an
    actual field, source passage or measured experiment.
2.  No fabricated precision: do not invent distributions, values,
    schemas, versions, results, links or thresholds.
3.  Preserve provenance: never describe a hybrid synthetic workload as a
    real enterprise trace.
4.  Separate levels: user sessions, application sessions, flows and
    packets are not interchangeable.
5.  Separate environments: Gymnasium approximations are not packet-level
    Mininet behaviour.
6.  Use measured underlay data; do not replace project measurements with
    generic values.
7.  Model transport honestly; a simplified rate equation is not a
    faithful TCP implementation.
8.  Measure switching effects; do not assign arbitrary switching loss
    probabilities.
9.  Validate before RL; policy results are not meaningful if
    workload/network dynamics are unvalidated.
10. Keep project scope intact. Do not remove an underlay, application
    class, offline RL stage, safety shield or testbed to make
    implementation easier. Explain and justify any proposed scope
    change.

## 10. Required response from the agent

After reading this file, the agent must return:

1.  A concise summary of changes from the previous plan.
2.  Unsupported claims removed or downgraded to assumptions.
3.  A corrected dataset audit table with verified repository links and
    file-level evidence.
4.  A prioritized task backlog with dependencies and exit criteria.
5.  Decisions that require the project owner's input.
6.  Tasks that can begin immediately without clarification.

**Do not merely paraphrase this document. Convert it into the active
project backlog and use it to guide subsequent technical decisions.**
