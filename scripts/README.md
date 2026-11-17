# Scripts

Experiment entrypoints and trace utilities. Entrypoints
(`run_baseline.py`, `train_offline.py`, `offline_sweep.py`,
`check_emulator.py`, `check_cql_cartpole.py`, `generate_datasets.py`,
`audit_offline_dataset.py`) are invoked directly, e.g.
`python scripts/check_emulator.py --help`; each bootstraps the repo
root onto `sys.path`, so no `PYTHONPATH` setup is needed. Trace
collection and preprocessing utilities are documented below.

`extract_sdncampus_distributions.py` downloads selected SDNCampus v1
application files, verifies their published SHA-256 values, and writes
flow-level summaries with bootstrap intervals. The output is not evidence of
mixed-application concurrency or session-level enterprise demand.
