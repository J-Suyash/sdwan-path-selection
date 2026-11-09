# SDNCampus Flow-Profile Extraction

Retrieved 2026-11-06 from the audited SDNCampus v1 release
(`10.17632/wvp9tksn72.1`). The extractor is
`scripts/extract_sdncampus_distributions.py`; the machine-readable results
and source identifiers are:

- `analysis/sdncampus_flow_profiles.csv`
- `analysis/sdncampus_flow_profiles.manifest.json`

## Method

Four representative application files were selected for the project classes:
`voip.csv` (voice), `googlemeet.csv` (video/conferencing), `gmail.csv`
(interactive/SaaS), and `dropbox.csv` (bulk). Each file contains 100,000
CICFlowMeter flow records. Source files were downloaded into the ignored
`data/raw/sdncampus-v1/` cache and verified against the SHA-256 values
published by Mendeley Data.

`Flow Duration` is recorded by CICFlowMeter in microseconds. The extractor
converts it to seconds, sums forward and backward packet lengths for total
flow bytes, and computes total-byte rate over positive durations. Median
intervals use 500 deterministic bootstrap replicates over up to 20,000 rows
per metric.

## Results

| Application | Class | Median duration (s) | p95 duration (s) | Median bytes | Median flow rate (Mbps) | p95 flow rate (Mbps) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| VoIP | voice | 0.1161 | 0.1199 | 2,236 | 0.1498 | 0.4947 |
| Google Meet | video | 0.1176 | 0.1198 | 26,627 | 1.9319 | 4.3102 |
| Gmail | interactive | 0.0190 | 0.0200 | 6,631 | 14.0515 | 64.9036 |
| Dropbox | bulk | 0.0746 | 0.1176 | 5,760 | 0.6818 | 5.4300 |

The short medians reflect CICFlowMeter records ended by timeout or connection
teardown, not application-session duration. Gmail and Dropbox records are
also predominantly unidirectional in this sample, so their flow rates are
burst measurements rather than complete request/response or transfer rates.

## Permitted use

These summaries can calibrate or cross-check flow-level rate, size and timing
assumptions for the corresponding applications. They do not establish:

- natural mixed-application concurrency;
- active-user or session-arrival rates;
- application-session duration;
- complete bulk-transfer size;
- request-rate or think-time distributions;
- enterprise-branch traffic composition.

The generator must therefore retain explicit assumptions for population,
session arrivals, session duration and concurrency until sources with those
levels are audited.
