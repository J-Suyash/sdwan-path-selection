# Corrected same-host clock-window mapping design

18 November 2026. Replaces the prior draft's packet mapping wording. Proposal only; no implementation, traffic or acceptance rule. The intended use is to place the measured monotonic endpoint window onto capture-frame arrival timestamps, not to reinterpret packet send times as capture arrival times.

## Corrected definition

A future timing-expanded run records explicit same-process clock checks. Before traffic starts and after drain/inspection, it atomically writes pairs `(epoch_s = time.time(), monotonic_s = time.monotonic())`. During the run it writes a fixed sparse sequence of additional pairs (for review: at least start, midpoint and end; the exact count is frozen before implementation and is not chosen from results). Each pair records the calls' execution order and adjacent operation timestamps so a sampling bracket is known. A pair is only a sampled association, not proof of simultaneity.

The explicit matched endpoint is already measured in monotonic time as `[t0, t1]`. Mapping means transforming those two window boundaries into estimated epoch-time intervals that can be compared with actual capture frame timestamps. Actual frame arrival epochs are never altered, and payload send time is not treated as frame arrival time.

For each boundary, the enclosing clock-check samples define an epoch estimate interval. With adjacent interior checks and drift bounded only as observed, the map must report an interval, not a point. The nominal estimate may use the enclosing marker interpolation, but acceptance metrics must use the interval: a capture frame is included only if its frame arrival epoch is unambiguously within the mapped window after mapping uncertainty; it is excluded only if unambiguously outside; frames whose timestamp overlaps uncertainty are counted in a separate `window_boundary_uncertain` category. The count/rate report therefore has a strict-inclusion count, strict-exclusion count and uncertain-boundary count. No outcome-derived tolerance is invented.

Sender sequence/send-time eligibility is a separate cohort predicate: a packet's sequence is eligible if its payload monotonic send time is in `[t0, t1]`. This eligibility is not used as an arrival timestamp. For UDP sender-side captures, payload monotonic send time and frame epoch can provide descriptive send-to-tap latency. That difference is not a clock-offset validation: it includes scheduling, packet construction, send system call and tap placement.

## Clock health checks

The metric is available only if all checks pass:

- Markers exist, are same-host and preserve call-order metadata.
- Monotonic timestamps are nondecreasing and epoch/monotonic samples have a plausible single-host relation; any wall-clock step or detected nonlinear adjustment makes mapped-window timing unavailable.
- Interior clock checks are independent samples, not a fitted line's zero residuals. With exactly two points, residuals are zero by construction and carry no validation. Interior checks measure observed drift/step evidence and bracketing.
- Frame timestamps are in the same epoch domain as the markers and have no backwards order beyond the documented packet reordering being studied.
- Capture process logs are retained and report zero kernel drops; otherwise frame-arrival counts are incomplete evidence.

The mapped result is labeled `mapped_capture_window`. It is descriptive, never application delivery, qdisc conservation, or packet delay. The monotonic matched endpoint remains the primary explicit window; both domains are retained.

## Verification before implementation approval

1. Offline synthetic clock tests with constant offset, known drift, known wall-clock step and deliberate sampling brackets: boundary filtering returns strict-in/strict-out/uncertain counts and nonlinear/step detection marks timing unavailable. Legacy metrics and drain behavior are unchanged.
2. Fake-capture tests prove payload send time is not used as frame arrival time.
3. Source review verifies each marker writer is atomic and records call order, and no system clock/NTP setting is changed.
4. Existing approved support run may be used only as format evidence, not as validation of clock offset: its sender-tap epoch-minus-send values include send-to-tap latency.
5. Future traffic still requires a separate scoped approval naming the timing-expanded batch. No approval is implied by this corrected design.

## Recommendation

Proceed only with this corrected timing-expanded design. Do not implement the previous draft. The actionable next step is bounded offline implementation plus tests, after parent confirms the correction is now the intended interpretation; then ask for one explicit five-run execution approval. If the user does not want more privileged runs, stop rather than collect a minimum batch that knowingly lacks timing evidence.
