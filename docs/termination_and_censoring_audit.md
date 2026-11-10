# Termination and censoring audit

Deliverable for verification spec section 2. Status: **PASS after fix**
(one defect found, failing test added first, fix applied, suite green).

## Defect found and fixed

**Defect (pre-fix):** FIN/RST records whose total bytes are
teardown-size (≤64 B, the release's 31 B teardown median) participated
in the payload-size bootstrap fit. This blended connection churn into
payload distributions: gmail's FIN-closed median was reported at 31 B
— a control frame, not a data transfer.

**Fix:** `summarize_transfer_group` now splits each (half, end) group
into `payload_rows` (> `TEARDOWN_MAX_BYTES = 64`) and
`teardown_only_rows` (≤64 B). Payload medians/percentiles/intervals use
payload rows only; teardown rows remain counted so connection churn
stays observable. Accounting invariant, regression-tested
(`test_payload_bearing_rows_survive_and_were_counted_once`):
`payload_rows + teardown_only_rows == transfer_rows` for every group.

**Failing test first:** `test_payloadless_fin_excluded_from_payload_fit`
was added before the fix and failed on the old behaviour
(`transfer_bytes_median == 31.0`); it passes after the fix.

## Post-fix evidence

From `analysis/sdncampus_transfer_summaries.csv` (seed 20261110,
500-replicate bootstrap):

| App | End | Rows | Teardown-only | Payload rows | Payload median (B) |
| --- | --- | --- | --- | --- | --- |
| dropbox | fin_rst | 474/491 | 302/302 | 172/189 | 482 / 656 |
| dropbox | censored | 49,505/49,530 | 1,223/1,161 | 48,282/48,369 | 5,760 / 5,760 |
| gmail | fin_rst | 1,792/1,796 | 1,693/1,696 | 99/100 | 567 / 552 |
| gmail | censored | 48,173/48,239 | 11,256/11,185 | 36,917/37,054 | 50,263 / 51,344 |
| googlemeet | fin_rst | 402/404 | 369/371 | 33/33 | 347 / 280 |
| googlemeet | censored | 49,661/49,533 | 613/639 | 49,048/48,894 | 27,132 / 27,225 |
| voip | fin_rst | 1,378/1,412 | 525/517 | 853/895 | 1,861 / 1,861 |
| voip | censored | 48,184/48,729 | 1,153/1,108 | 47,328/47,621 | 2,236 / 2,236 |

(Values are estimation half / held-out half.)

## Findings

1. **Teardown records dominate FIN/RST classes** for gmail (94%) and
   googlemeet (92%): most observed FIN/RST records are pure teardowns.
   The payload-bearing FIN medians (280–1,861 B) describe
   short-but-real transfers, not connection control traffic.
2. **Censoring is the dominant termination mode by row count** (~97%
   of rows per application are `censored`, i.e. no FIN/RST observed in
   the record). This is consistent with the release's flow-record
   construction, not with abnormal application behaviour; the two
   classes are never merged.
3. Gmail teardown-only counts are an order of magnitude above the other
   apps (≈11k vs ≈0.6–1.2k) — churn-heavy behaviour that would have
   been invisible had teardowns been blended into the payload fit.

## Limitations

- `TEARDOWN_MAX_BYTES = 64` is a documented modelling threshold, not a
  source field. Its sensitivity was measured (2026-11-10,
  `analysis/teardown_cutoff_sensitivity.csv`; per-cutoff artefacts at
  32/64/128 B with manifests): see the next section.
- The release has no timestamps, so teardown *rates* over time are not
  recoverable — only per-record classification.

## Cutoff sensitivity (32 / 64 / 128 B)

Re-ran the full extraction at each cutoff (same seed 20261110, same
split; per-cutoff outputs and manifests committed). Estimation-half
results for the FIN/RST class, where the cutoff bites:

| App | Teardown rows (32/64/128) | FIN median B (32/64/128) | Censored median B (32/64/128) |
|---|---|---|---|
| dropbox | 296/302/362 | 444/482/656 | 5,760 / 5,760 / 5,760 (identical) |
| gmail | 1,649/1,693/1,712 | 213/567/725 | 47,396 / 50,263 / 52,972 (±5.5%) |
| googlemeet | 352/369/375 | 141/347/620 | 26,969 / 27,132 / 27,663 (±1.3%) |
| voip | 525/525/531 | 1,861 / 1,861 / 1,861 (identical) | 2,236 / 2,236 / 2,236 (identical) |

**Justification of the selected 64 B cutoff:**

1. The measured teardown peak is 31 B (pure control frames); 64 B is
   2× that median and clears the pure-control band with margin.
2. The 32–64 B band holds only ~2.5% of gmail FIN rows (44 of ~1,800):
   classification there is genuinely ambiguous, and the 64 B choice
   keeps them as teardowns consistent with the 31 B peak.
3. Payload-bearing FIN medians are ≥280 B (googlemeet held-out), so 64
   B never truncates a clearly payload-bearing population.
4. **Generated workload impact: none today.** `env/workload.py` is
   rate-based (`DEFAULT_BRANCH_PROFILES`, explicit assumptions); the
   transfer summaries are evidence for future profile updates, not
   direct inputs. The censored-median movement (≤5.5% gmail, ≤1.3%
   meet, 0% others) bounds the effect when those profiles are
   eventually recorded in `docs/parameter_registry.csv`.

The original source CSVs are untouched (read-only extraction with
sha256-pinned provenance in every manifest); all three cutoff outputs
are retained, and the canonical artefact
(`analysis/sdncampus_transfer_summaries.csv`) records its cutoff in the
per-row `teardown_max_bytes` column and the manifest.
