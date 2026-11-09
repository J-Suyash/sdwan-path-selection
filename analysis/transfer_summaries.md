# SDNCampus Held-Out Transfer-Level Summaries

Produced 2026-11-10 (owner decision 7). Script:
`scripts/extract_sdncampus_transfer_summaries.py`; machine-readable
outputs:

- `analysis/sdncampus_transfer_summaries.csv`
- `analysis/sdncampus_transfer_summaries.manifest.json`

## Method

The audited SDNCampus v1 CSV files (100,000 CICFlowMeter records per
application) carry no flow identity: IPs, ports and IDs are stripped and
there are no timestamps. Each record is therefore keyed by its own
duration/byte/flag measures plus row position, and split by salted md5
parity (seed 20261110) into an estimation half (~50,000 rows) and an
independent held-out half.

Each record is classified by observed connection end:

- `fin_rst` — FIN or RST flag counts > 0 (teardown observed);
- `censored` — no teardown flags (timeout- or capture-censored).

Bootstrap median intervals (500 replicates) are computed on the
estimation half only; the held-out half is reported for replication.

## Results (median transfer bytes per continuation, estimation half)

| Application | Class | end | median B | 95% bootstrap CI | held-out median |
| --- | --- | --- | ---: | --- | ---: |
| VoIP | voice | fin_rst | 1861 | [1861, 1861] | 1861 |
| VoIP | voice | censored | 2236 | [2236, 2236] | 2236 |
| Google Meet | video | fin_rst | 31 | [31, 31] | 31 |
| Google Meet | video | censored | 26,830 | [26,268, 26,986] | 26,861 |
| Gmail | interactive | fin_rst | 31 | [31, 31] | 31 |
| Gmail | interactive | censored | 11,152 | [8364, 11759] | 11,403 |
| Dropbox | bulk | fin_rst | 31 | [31, 31] | 31 |
| Dropbox | bulk | censored | 5760 | [5760, 5760] | 5760 |

Held-out medians reproduce the estimation half to within ~1% for the
payload-bearing groups, which supports stability of the split choice.

## What the numbers mean

- **FIN-closed records are teardown-only.** The modal FIN/RST record
  carries 31 bytes across gmail/meet/dropbox (1861 B for voip frames).
  Application payload in this release lives in what CICFlowMeter records
  as timeout-closed continuations. The generator must therefore treat
  these as measured *burst sizes for periodic/keep-alive-scoped traffic*
  and not as complete objects.
- **No complete-object evidence.** Gmail-censored continuations ($\sim$
  8.4–11.8 kB median, wide right tail, p95 $>$ 150 kB) are flow
  continuations, not emails. Complete bulk-transfer size remains
  **unavailable** from this source; the parameter registry claim stands.
- **Session level is still unavailable**, and now the reason is
  download-level verified: the audited CSVs contain no user/device/session
  identity at all, so nothing in this release supports session-arrival or
  session-duration extraction. Session-level parameters stay explicit
  assumptions in the generator.

## Permitted use

Calibrate or cross-check per-application continuation burst volume
(voice payload ≈ 1.8–2.2 kB; short interactive bursts ≈ 11 kB; video
keep-alive bursts ≈ 27 kB at the meet rate; bulk scenes distribute around
5.8 kB with heavy upper tail). Do **not** use these as session
durations, session arrivals, object sizes, or evidence of mixed
application concurrency.
