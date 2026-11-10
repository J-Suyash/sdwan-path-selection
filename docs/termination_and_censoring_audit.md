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
  source field. It is set above the observed 31 B teardown median and
  below the smallest payload-bearing medians (280 B); the sensitivity
  of the medians to the exact cutoff (e.g. 32 vs 128 B) has not been
  swept.
- The release has no timestamps, so teardown *rates* over time are not
  recoverable — only per-record classification.
