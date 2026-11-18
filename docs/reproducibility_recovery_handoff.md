# Reproducibility recovery handoff

## Current state (2026-11-18 ~06:05 IST, final checkpoint)

- Latest code commit `28a58b5` (testbed: suffix-aware qdisc backlog parse,
  zero-inclusive first bucket); full suite 157 passed in 137.65s at this
  code state. `5a2b98c` and this final edit on top are docs/comments
  only. Worktree clean except the intentional `data/raw`,
  `data/processed` symlinks.
- New evidence (local, candidate-only): occupancy normalization impact
  (`/home/sxtr/queue_delay_baseline_evidence_v3.json`), e11-r00 repair
  band impact three-way (`/home/sxtr/e11_band_impact_v2.json`):
  committed bands are bit-identical under original pipeline,
  zero-edge-only, and suffix+edge repairs.
- New finding: v1 cell e11 audit trail was distorted by the tc
  Kb-suffix parse defect (e11-r00 recorded occupancy 0.0, true backlog
  241Kb = 246784 +/- 15 B, per the iproute2 suffix convention sourced
  from public main with installed-version match not proven - see the
  tc-convention bullet below); band numbers provably insensitive.
- Aggregate-table impact (`/home/sxtr/aggregate_impact.json`):
  original pipeline reproduces the retained calibration_stats.csv rows
  bit-exact for both rounds and exclusions match both manifests;
  zero-edge-only relabels only the e11 nan singleton to 'empty';
  suffix+edge unifies v1 cell e11 (24 rows) with small stat shifts
  (loss mean 0.01808 -> 0.01995, reordering mean 0.00932 -> 0.00988,
  interruption mean ~unchanged); v2 unaffected. Exclusions unchanged.
- Open mechanical finding (candidate evidence, owner decision pending,
  no fix applied): the emulator's switching query converts queue
  occupancy bytes with a fixed 1500 B (`env/sdwan_env.py:183`,
  `packets_in_flight=occupancy / 1500.0`), while the calibration
  column it queries was computed as bandwidth-delay product with the
  workload's actual packet size (testbed/run_switch_calibration.py:308,
  packet_bytes 240/1200/1400) - the same convention the b325289 fix
  corrected on the testbed side. Two divergences: fixed 1500 B vs
  actual packet size (6.25x for 240 B voice, 1.25x for 1200 B, 1.071x
  for 1400 B), and wire BDP vs queued backlog as the named quantity.
  `SwitchingModel.predict` (env/switching.py) is nearest-neighbour over
  six normalised features with no convention or range guard and no
  failure path, so a wrong-convention query silently selects
  neighbours. Docs disclose the corrected testbed convention
  (docs/switching_calibration_report.md:78, docs/testbed_match.md:30)
  but not the emulator's residual 1500 B. Committed calibration
  artefacts are unaffected (testbed side); impact is limited to
  emulator-vs-testbed switching-transient comparability.
  Method evidence (read-only, existing artefacts): both conventions
  were introduced 2026-11-10 00:56 (emulator e41d64f, testbed 5b74c6f);
  b325289 (15:31) fixed only the testbed's queue-limit conversion.
  docs/workload_model_spec.md:73 names 'packets in flight' as a
  nearest-neighbour covariate without defining its semantics or unit,
  so neither reading is contractually wrong. Calibration ranges
  (committed data/switching_calibration.csv bdf331a8 and _v2.csv
  d7ee403c, 119 rows each): voice udp 4.84-14.64, video udp
  12.59-38.07, interactive tcp 25.83-78.08, bulk tcp 110.71-334.64
  packets (BDP with actual packet_bytes). Emulator query = backlog
  bytes/1500: default buffers are cap_mbps*0.25 s/8 (bb/leo 6.25 MB,
  five_g 9.375 MB), so query = frac*4166.7 (bb/leo) or frac*6250
  (five_g); at the observed max occupancy frac 0.164 that is 683-1025
  'packets', beyond the calibrated maximum 334.64; voice queries
  leave the calibrated voice range once backlog exceeds ~22 kB
  (14.64*1500 B) and fall below its minimum under ~7.3 kB.
  The NN distance scale for this feature is median 31.25, so such
  query values dominate the six-feature distance. The mismatch is
  exercised only when a calibration CSV is supplied: default
  switching_calibration_path=None (zero effects, calibrated=false);
  scripts/decompose_sla_violations.py:103 and
  scripts/reassess_delay_semantics.py:54 enable it via --calibrated.
  Provenance of committed analysis CSVs wrt --calibrated unverified.
- tc suffix convention sourced from iproute2 lib/json_print_math.c
  sprint_size (public main; installed package is 7.3.0-1.1 and matches
  on all 960 observed tokens, version match not proven): K/M/G are
  1024-based, suffix prints only within +/-15 B of a unit multiple.
- v1 scenario hash conflict explained: current scenario file has
  per-path limits added; `scenario_as_run.json` (shared 1000) plus all
  120 qdisc `limit 1000` lines corroborate the as-run config; edit
  timing unknown.
- The cumulative patch and all artifact hashes ship in a separate
  checksum artifact delivered alongside this handoff, kept out of the
  committed document to avoid a self-referential hash.

### Operational detail (verified earlier this session; see the final checkpoint above for current figures)

- Branch `instinct/reproducibility-diagnostics` tip
  (worktree `/home/sxtr/Projects/Major Project-instinct-recovery`),
  clean except two intentionally retained untracked symlinks,
  `data/raw` and `data/processed`, pointing at the main checkout's
  data. Nothing pushed or merged.
- Full suite: **150 passed**, one known SciPy KS asymptotic warning,
  142.85 s (measured at 4461cbe). SUPERSEDED: 157 passed in 137.65 s at
  `28a58b5` (see final checkpoint above); 28a58b5 changed testbed code.
  The 86-test and 97-test figures below are historical checkpoints,
  not current state.
- Re-run in the existing worktree (verified this session):
  ```bash
  cd "/home/sxtr/Projects/Major Project-instinct-recovery"
  "/home/sxtr/Projects/Major Project/.venv/bin/python" -m pytest -q
  ```
  The worktree reuses the main checkout's virtualenv; the `data/raw`
  and `data/processed` symlinks already exist and are intentionally
  retained. Verified: 150 passed at 4461cbe; re-verified after the
  28a58b5 testbed code change: 157 passed in 137.65 s. Only 5a2b98c
  and c546e72 sit on top, both documentation/comment-only.
- Fresh-clone setup (documented in README/Setup, NOT retested this
  session): `uv` venv creation, requirements install, then the two
  data symlinks, then `python -m pytest -q`. The suite was not run
  from a truly fresh environment in this round, so the fresh-clone
  path is expected-but-unverified, not an exact verified reproduction.
- Without the data links the suite runs in synthetic-fallback mode:
  the SLA-decomposition verification now fails loudly with a named
  error (`allow_synthetic_traces=False`) instead of comparing
  meaningless counts, and the provenance tests skip with an explicit
  reason.
- Evidence availability differs by layer. Committed (in git, hashed):
  the per-run raw CSVs (`data/switching_calibration.csv` sha256
  bdf331a8..., `_v2.csv` d7ee403c...), the repeatability JSONs
  (including per-repetition values), and the derived thresholds CSV.
  Local-only (untracked `testbed/outputs/`, not in git): per-run
  `metrics.json` (266 files), per-packet `sender.csv`/`receiver.csv`
  and `traffic.pcap` for all 240 calibration runs of both rounds.
  The candidate-statistic comparison of 2026-11-18 used only the
  committed CSVs; the local per-run metrics corroborate (e00-r00
  interruption_s=1.8579 in both).
- Legacy D1-D3 parse check (2026-11-18): the 216 legacy parquet files
  parse individually, but `offline.learner.load_transitions` and
  `build_mdp_dataset` refuse them by design (`dataset has no
  behavior_action_prob; regenerate ... before WIS`). This is a
  mechanical parsing result only; it says nothing about RL/OPE
  eligibility, which remains gated on regeneration after cross-engine
  validation.
- Open scientific gates (unchanged owner decisions; engineering test
  counts do not bear on them): band statistic choice; candidate band
  acceptance; `queue_delay_ms` residual-proxy acceptability after
  empty-queue baseline validation; Mininet sag realization, trace
  windows and packet-size transfer; the `e00-r00` interruption-outlier
  ruling; team-collected broadband redistribution approval;
  cross-engine validation; final review.

## Scope and safety

Work is isolated on `instinct/reproducibility-diagnostics` in a separate worktree. The original checkout remains on `main`. Nothing has been pushed or merged. Existing datasets and checkpoints have not been overwritten. This handoff reports developer diagnostics, not completed research, deployment acceptance or publication readiness.

## Fixed and tested

Two direct script entrypoints could not import the flat repository when invoked normally. A small repository-root import bootstrap fixes `scripts/audit_offline_dataset.py` and `scripts/generate_datasets.py`. No algorithm, arguments, dataset policy, or validation gate changed.

Two regression tests invoke the absolute script paths with `--help` from an unrelated temporary directory, remove `PYTHONPATH`, and check for successful usage output. Both passed. No data is generated by those tests.

A new stdlib-only `scripts/repro_preflight.py` checks the expected source files before a run. Its default path is anchored to the repository, not the shell directory; `--data-root` overrides it. `--json` emits explicit version/file-status booleans and `--hash` computes chunked SHA256. Its output deliberately says `check_mode=file_presence_only` and `scientific_validity=not_evaluated`. Fake bytes can pass presence checks: this utility does not validate parquet, provenance, licensing or scientific quality. Nine regression cases cover missing/empty/directory inputs, hash-read failure, Python-version mismatch, stable default paths, relative overrides and CLI usage. Independent review caught and corrected a hash-error false-success bug before acceptance.

## Recovery-worktree verification (historical checkpoint, mid-recovery)

After the support fixes and new tests, the full suite passed **97 tests with one SciPy KS asymptotic warning in 51.32 seconds**. The targeted 11-case support suite also passed. The actual local presence/hash preflight returned success for all three expected processed inputs under Python 3.11.15. These input hashes were computed on the laptop; no raw traffic rows were included in model prompts or the handoff. Superseded: the data symlinks were later recreated and are intentionally retained (see Current state). Use `--data-root` with the original processed-data directory for the standalone preflight when running without them.

## Verified baseline (historical checkpoint at base commit)

At base commit `c57e91b17ac60345ff0c9bcd616aceba7b1de624`, the existing suite passed all 86 tests with local traces. One SciPy KS-test warning switches its exact calculation to an asymptotic method. Python was 3.11.15. This is a test-suite result, not proof that the simulator is scientifically valid.

The fixed-count SLA-decomposition test fails in a fresh clone without ignored trace data, but passes with the laptop's processed traces at the same commit. At that time, missing input files triggered a silent synthetic fallback; since 4461cbe this verification sets `allow_synthetic_traces=False` and fails loudly instead. This is a trace-dependent integration test, not a self-contained unit test. Do not change its expected counts simply to make a data-less clone pass.

## Data layers and evidence

Public link traces and local D1-D3 transition logs are different layers. D1-D3 were generated locally by an older emulator pipeline. Replacing downloaded traces would not repair missing metadata in those generated logs.

Schema-only inspection covered all 216 local legacy files:

| Dataset | Files | Rows | Current provenance fields missing in every file |
|---|---:|---:|---|
| D1 | 40 | 144000 | behavior_action_prob, policy_version, seed, simulator_version, workload_profile, workload_regime |
| D2 | 80 | 288000 | same six fields |
| D3 | 96 | 345600 | same six fields |

All files were readable at the metadata level. That does not establish valid trajectory values or adequate action support. No missing fields were fabricated or backfilled.

The current generator was tested in one small preliminary D1 episode (seed 0, medium profile, normal regime) into a separate temporary directory. It emitted 3600 transitions with the current provenance fields, trace segment and split group. The current auditor accepted the schema. Only two of 81 actions were observed, which is not sufficient evidence of offline-learning coverage. The temporary outputs were deleted; the original D1-D3 files were unchanged.

## Final generation remains gated

There is no local `data/cross_engine_validation_acceptance.json`. A `--finalize` attempt was tested with a temporary destination: it refused with exit 1 and created no output directory. Keep that behavior. Existing switching-calibration sweeps are not the same as reviewed cross-engine acceptance.

Do not train on or present legacy checkpoints as current validated results. Four checkpoint files exist locally, but compatibility and scientific usefulness were not established and they were not deserialized during these diagnostics.

## Repeat the developer checks

From the recovery worktree, use the existing Python 3.11 environment or a separately installed compatible environment:

```sh
python -m pytest -q -p no:cacheprovider tests/test_cli_entrypoints.py tests/test_repro_preflight.py
python scripts/repro_preflight.py --json
python scripts/repro_preflight.py --data-root /path/to/processed --json --hash
python scripts/audit_offline_dataset.py --help
python scripts/generate_datasets.py --help
```

The complete existing suite requires the processed traces for its fixed-count integration test. Raw and processed data are intentionally untracked. Never commit traffic data, credentials, model files, or temporary worktree data symlinks.

## Next research decisions, not completed work

1. Verify and document cross-engine acceptance against the actual code, configuration and trace fingerprints.
2. Only after that gate, regenerate final transition datasets with real provenance and audit support/splits before training.
3. Review whether the cost-only reward, observed state and baseline behavior match the intended constrained objective. These are method decisions, not silently changed by the infrastructure repair.
4. Compare learning against strong baselines on held-out regimes with a prespecified practical improvement and paired uncertainty. Do not tune on the held-out data.
5. Freeze reproducible results before preparing the final demo, paper and slides. A negative learning result can still be an honest evaluation result; it does not by itself prove OPE is unreliable.

## Remaining limitations

No full training, new cross-engine sweep, deployment test, paper or slide completion was attempted. Public-source licensing and redistribution decisions remain separate from local test success. The short collected broadband input and source-specific missing measurements need coverage/semantics review. A running tunnel proves access, not unattended persistence through laptop sleep or reboot.

## Final infrastructure checkpoint

After the comparator-only repair and 28 new CLI regression cases, the complete suite passed **125 tests with one existing SciPy KS warning in 114.13 seconds**. The earlier 97-test result remains the first checkpoint, not the final count. Comparison functions and default output path were independently AST-compared to the base revision and are unchanged. The original checkout remains clean on main; all changes are local to the same recovery branch. No scientific acceptance record or final datasets were created.

## Comparator CLI modes and limits

The existing `scripts/cross_engine_compare.py` is a report tool by default, not a whole-round acceptance gate. Existing repository callers were inspected: tests import its statistical functions and documentation names the script; no repository automation invokes its CLI. The default report behavior is preserved for valid paired inputs, including exit 0 when some comparisons reject. The CLI now labels that mode explicitly.

Use `--check` when a shell pipeline needs failure on any rejected comparison in the supplied paired tables:

```sh
python scripts/cross_engine_compare.py \
  --emulator /path/to/emulator.csv --mininet /path/to/mininet.csv \
  --thresholds analysis/cross_engine_thresholds.csv \
  --out /path/to/comparison.csv --check
```

Exit codes: 0 for a completed report in default mode, or all supplied comparisons accepted in `--check` mode; 1 for rejected comparisons in `--check` mode; 2 for invalid input or an output I/O failure. An invalid input does not write a new partial report. The statistical functions, current thresholds and existing result columns are unchanged. Before computing, the CLI checks required columns, nonempty tables/identifiers, finite numeric values, symmetric case/metric pairs, and finite nonnegative unique threshold bands for every supplied metric. Extra unrelated threshold metrics remain permitted.

`--check` does not verify the full expected manifest, five-replicate adequacy, matched configuration, trace provenance or reviewer authority. Passing one supplied case does not mean all four required cases ran. It never writes an acceptance record.

### Existing scientific-workflow gaps remain

Read-only fixture diagnostics at the base revision found:

- The four-case JSON is a case manifest, not a scenario accepted directly by `testbed.scenario.load_scenario`; direct loading fails because its `paths` field is absent. Executable scenario mapping remains work to review, not silently invented here.
- The manifest requests `queue_delay_ms`, `throughput_mbps`, `delay_median_ms` and `jitter_mean_ms`, but current threshold bands cover only `interruption_s`, `loss_frac` and `reordering_frac`.
- The acceptance-file helper requires nonempty fields but does not independently bind their values to actual revisions, inputs or case coverage. A helper returning true is not a scientific review or authorization.
- The threshold code uses half-range while describing maximum deviation from the median. For skewed replicates `[0,0,0,0,10]`, the latter is 10 but the implemented half-range is 5. This mathematical-method issue needs review; no formula or bands were changed by the CLI repair.
- Recomputing bands from both committed calibration summary files exactly reproduces the committed numeric bands (48 included cells). Documentation saying that recomputation is pending is stale. The per-path summary records 24 cells and 119 observed runs, not proof that all 120 planned runs completed.
- The matched-mode queue-byte override and tests already exist despite a stale plan saying otherwise.

These diagnostics use controlled fixtures, not new measured cross-engine results. They must not be copied into an acceptance file as if they were measurements.

## Follow-through, 2026-11-18 (threshold naming, manifest diagnostic, smoke run)

### Threshold band naming made honest

The derive script's band statistic was implemented as the per-cell
half-range `(max - min) / 2` but labelled "max deviation from median";
for skewed replicates the two differ by up to a factor of two. The
script now emits `cell_half_range_median/q90/q95` with the caveat in
its docstring, computing exactly the same numbers as before. The
comparator accepts the honest column first and the legacy column as a
backward-compatible fallback, with input errors naming both. New
`tests/test_threshold_labels.py` covers new-name acceptance, legacy
acceptance, precedence when both exist, the missing-column input error,
a synthetic half-range pin (min 0 / max 10 -> 5.0, not 10), and a
regression proving the committed thresholds CSV is bit-exact
reproducible from the two committed repeatability summaries. Choosing
the statistic (half-range vs true maximum deviation from the median)
remains an owner decision; no formula or committed band changed.

### Manifest gap diagnostic

New stdlib-only `scripts/cross_engine_manifest_check.py` reports,
mechanically, what the case manifest still needs before the runner
could execute its cases: missing runner-schema sections, per-case
queue-config coverage, band coverage per requested metric (either band
column name accepted), and reference-scenario consistency. It performs
no scientific validation, constructs no scenarios and writes no files;
exit 1 with gaps, 0 when clean, 2 for invalid inputs. Five regression
tests cover the committed manifest's current gaps, a runner-shaped
synthetic exit-0 path, unreadable input and a band-column-free
thresholds CSV.

### Acceptance-artefact revision binding enforced (engineering only)

`validation_is_accepted` now enforces its documented exact-code-revision
contract: the recorded `code_revision` must be a hexadecimal commit
object name (full or unambiguous abbreviation; tags, branches, `HEAD`
and revspecs are rejected before git is invoked, and the recorded
string must be a genuine prefix of the resolved id so an all-hex tag
cannot impersonate a different commit), resolved with
`git rev-parse --verify --quiet <recorded>^{commit}` at the explicit
repository root, and equal to HEAD at gate time. The tracked working
tree must be clean (untracked files such as data/ do not count). Every
failure mode fails closed. This is mechanical precondition enforcement,
not scientific acceptance: config_fingerprints contents,
trace_set_sha256 contents, case coverage and reviewer authority remain
unverified, as does untracked importable code. Tests use both mocks and
real temporary git repositories (moving-ref bypass, hex-tag
impersonation, dirty checkout, wrong cwd, immutability across a
docs-only commit). No acceptance artefact was created.

### Mininet smoke execution check (one approved run)

With the owner's go-ahead, the committed smoke scenario was run once
via sudo: conflict precheck (only the user's preexisting `s1` bridge
existed; it was not touched), one scoped privileged invocation, and
trap-based cleanup of only this run's resources. The run completed
(RUNNER_RC=0): output at `testbed/outputs/smoke-20261118-033510/`
(switch_metrics_raw.csv, run_manifest.json, per-run capture), marked
raw_unvalidated by the runner itself. This verifies the execution path
(OVS bridges, namespaces, TC netem, OpenFlow controller, synthetic
capture) works end-to-end on this laptop; it is not a validation
measurement. Post-run sweep found no leftover processes, veth links,
TC qdiscs, namespaces or controller port bindings; the runner's own
self-cleanup removed its bridges. Note: `openvswitch-switch.service`
does not exist on this system (`is-active` reports "inactive" for
unknown units); OVS works through another unit, so no service state
was changed or needed restoring. The sudo credential was supplied from
the owner's vault via a short-lived 0600 stdin file, deleted on exit,
with the sudo timestamp revoked afterward; no secret persisted.

### Band candidates for the uncovered metrics (unreviewed)

The committed raw calibration runs already record `delay_median_ms`,
`delay_p95_ms`, `jitter_mean_ms` and `throughput_mbps`; the aggregator
never carried them through. Candidate bands for the three measurable
metrics were derived from the committed raw runs under both statistics
and stored outside the repository as diagnostics (not committed, not
installed in any gate, explicitly UNREVIEWED). `queue_delay_ms` is not recorded directly. A
run-level residual-delay proxy (`delay_median_ms` minus the configured
static path delay) is computable from the committed raw CSVs, and the
current runner retains per-packet sender/receiver CSVs (verified in the
2026-11-18 smoke output) - but the committed calibration rounds retain
only metrics.json and qdisc snapshots per run, so per-packet
decomposition was believed possible only for future runs; that was wrong: all 240 local calibration run dirs (both rounds) retain sender.csv/receiver.csv per-packet logs and traffic.pcap, so decomposition is possible for existing runs. Caveats for that analysis: timestamps are host time.monotonic() (single host, namespaces share the clock); matching is a sequence inner-join with last-wins on duplicates; lost packets are excluded from delay statistics; sender.csv's received_at column is an echo of sent_at (only receiver.csv received_at is real); and the near-empty occupancy bucket is a candidate reference (low pre-switch qdisc backlog), not a proven empty-queue baseline. The proxy's semantics
differ from the emulator's occupancy/service-rate queue delay and it
includes serialization and host-scheduling overhead (1400 B at the
6 Mbps floor is ~1.87 ms of serialization), so it needs an empty-queue
baseline validation before use as a matched metric. Whether
calibration-derived bands transfer to case conditions, and the
statistic choice, are owner decisions.

### Still pending owner decisions

1. Band statistic: half-range vs true maximum deviation from the cell
   median (the mislabel means the documented intent is ambiguous).
   Changing the statistic changes the acceptance criterion and needs an
   explicit recorded owner decision - no silent fallback. Evidence
   update 2026-11-18: the committed repeatability JSONs store
   per-repetition values, so both statistics are computable from
   committed hashed inputs; an uncommitted comparison artifact
   (/home/sxtr/band_stat_compare_v2.json, script attached to the same
   report) reproduces the committed bands bit-exactly and tabulates
   both candidates with the e00-r00 outlier in and out. The committed
   bands embed e00-r00, whose ruling is still open, so that ruling
   changes the band values.
2. Acceptance/installation of candidate bands for the three metrics.
3. `queue_delay_ms`: whether the residual-delay proxy is acceptable
   after empty-queue baseline validation, given its different semantics
   from the emulator's occupancy/service-rate delay.
4. `capacity_floor_frac` semantics are now pinned by evidence: the
   emulator floors trace capacity at 0.2x nominal (env/traces.py:66,
   pinned by test_queue_delay_ceiling_from_capacity_floor), matching
   the manifest's 0.2. Remaining choices: how Mininet realizes sagged
   capacity (static TC at floor rate vs time-varying), which emulator
   trace windows cases use, and packet-size transfer effects.
5. Final review and acceptance of any validation round.

## Engineering follow-through 2026-11-18 (commits de9b28b, 4461cbe)

Post-handoff, non-scientific defects fixed on the same branch; no
scientific behavior, threshold or acceptance question was changed.

1. CLI import bootstrap: `run_baseline.py`, `train_offline.py` and
   `offline_sweep.py` failed with `ModuleNotFoundError: env` unless
   `PYTHONPATH=.` was set. All direct entrypoints now carry the same
   repo-root bootstrap as `generate_datasets.py`/`audit_offline_dataset.py`,
   and `tests/test_cli_entrypoints.py` guards all seven from a foreign
   working directory with `PYTHONPATH` removed.
2. `check_emulator.py` and `check_cql_cartpole.py` had no argument
   parsing: `--help` executed a full emulator episode / a full training
   run. Both now parse arguments first and `--help` is nonexecuting.
3. `check_emulator.py` asserted a 4.0 s episode wall-clock budget (an
   Apple M1 target) and exited nonzero on this laptop (4.91 s) despite a
   clean episode. The benchmark is now opt-in
   (`--benchmark [--benchmark-seconds N]`); elapsed time is always
   reported, never asserted by default.
4. Trace provenance: `env/traces.py` silently returned synthetic series
   when the processed parquets were missing or unwindowable. `reset()`
   now records per-underlay `trace_provenance` ("real"/"synthetic") and
   surfaces it with `trace_window_start` in every `info` dict;
   `SDWanConfig.allow_synthetic_traces=False` refuses the fallback with a
   named error; `test_sla_decomposition.py` requires real inputs;
   `tests/test_trace_provenance.py` pins labelling and refusal; the
   README documents the `data/raw` + `data/processed` symlink dependency
   for fresh clones/worktrees.

### Incident record (2026-11-18)

- 04:05 IST: while probing entrypoints,
  `python scripts/check_cql_cartpole.py --help` executed a 5-epoch CQL
  CartPole training (the script ignored `--help`) and wrote
  `d3rlpy_logs/` into the worktree. The directory was deleted and
  `git status` was verified clean afterward (no other writes detected
  in the worktree). The run trained a toy CartPole policy unrelated to
  project data; its output is not referenced by any result. Item 2
  fixes the defect class.
- ~04:15 IST: the full suite failed
  `test_sla_decomposition.py::test_decomposition_reproduces_violations_from_raw_transitions`
  ([11, 1137, 10] vs committed [80, 952, 1]) because the untracked
  `data/raw` + `data/processed` symlinks had been removed after the
  previous green run and the emulator silently synthesized traces. The
  symlinks were recreated (untracked, read-only use of the main
  checkout's data) and left in place deliberately; the failure mode
  motivated item 4.

Test state: 147 passed at de9b28b; 150 passed at 4461cbe (142.85 s, one
known SciPy warning). These are engineering regression tests; they do
not validate any scientific conclusion, and every acceptance question in
"Still pending owner decisions" above remains open.
