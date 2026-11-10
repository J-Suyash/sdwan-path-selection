# Held-out split verification

Deliverable for verification spec section 1. Status: **PASS with stated
limitations**. Every claim below is backed by a test in
`tests/test_heldout_split.py` (10 tests, passing) and by the committed
artefacts `analysis/sdncampus_transfer_summaries.csv` and
`analysis/sdncampus_transfer_summaries.manifest.json`.

## The guarantee under test

The SDNCampus v1 release (`10.17632/wvp9tksn72.1`) strips user, device,
session and flow identity columns, and carries no timestamps. A
session-level or flow-level holdout is therefore **not derivable** from
this source. The guarantee this pipeline provides is a **deterministic
row-level holdout** over the source frame:

> Partition membership of a flow-record row is a pure function of
> (salted md5 of its measured duration/byte columns plus its row index,
> seed 20261110) — deterministic, reproducible, and independent of any
> label or outcome field.

This is the strongest split the release supports. The manifest records
`"unit_of_analysis": "flow continuation burst; not a session"`.

## Key construction

- Key columns: `Flow Duration`, `Total Length of Fwd Packet`,
  `Total Length of Bwd Packet` (`SPLIT_KEY_COLUMNS` in
  `scripts/extract_sdncampus_transfer_summaries.py`).
- **`FIN Flag Count` and `RST Flag Count` are excluded**: they partly
  determine the `connection_end` label, and the spec forbids labels in
  the split key. Regression test:
  `test_split_is_not_label_dependent`.
- Row index is part of the key so identical measured records can land
  in different halves (`test_row_index_breaks_identical_record_ties`).
- Salt: `20261110`; hash: md5 parity. The manifest pins each source
  file's sha256, so any re-download or reordering of rows is a new
  split version, not a silent reshuffle (`test_source_order_is_stable_before_split`).

## Partition properties

| Property | Test |
| --- | --- |
| Deterministic under repeated hashing | `test_split_is_deterministic` |
| Disjoint, exhaustive, no row lost or duplicated | `test_split_partitions_all_eligible_rows_once` |
| Changing a measured field changes hash input | `test_changed_measured_field_changes_hash_input` |
| Estimation/held-out fractions reported per (half, end) group | `test_held_out_fraction_reported_per_group` |
| Group counts reconcile to source rows | `test_classify_counts_reconcile_to_source_rows` |

## Replication results (estimation vs held-out medians, bytes)

| Application | End | Estimation median | Held-out median |
| --- | --- | --- | --- |
| dropbox | fin_rst | 482 | 656 |
| dropbox | censored | 5,760 | 5,760 |
| gmail | fin_rst | 567 | 552 |
| gmail | censored | 50,263 [48,919–51,943] | 51,344 [50,026–52,701] |
| googlemeet | fin_rst | 347 | 280 |
| googlemeet | censored | 27,132 [26,711–27,391] | 27,225 [26,581–27,330] |
| voip | fin_rst | 1,861 | 1,861 |
| voip | censored | 2,236 | 2,236 |

Held-out medians replicate the estimation medians within bootstrap
intervals for the censored (payload-bearing) classes; fin_rst medians
agree within the small-sample spread of teardown-adjacent records.

## Limitations

1. **Row-level, not session-level.** Two rows of one real session can
   straddle the halves. The release makes better impossible; downstream
   users must not treat the halves as session-disjoint.
2. **Index dependence.** The split depends on source row order. The
   sha256 pinning in the manifest detects any change.
3. Teardown-only records (≤64 B) are excluded from payload statistics
   and counted separately — see `docs/termination_and_censoring_audit.md`.
