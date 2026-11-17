#!/usr/bin/env python3
"""Developer preflight helper: confirm expected source parquet files exist.

This is a file-presence utility for reproducibility setup only. It does NOT
read or validate parquet contents and makes no claim of scientific readiness.

Usage:
    python scripts/repro_preflight.py [--data-root PATH] [--json] [--hash]

Exit codes:
    0  Python is 3.11 and all expected files exist as nonempty regular files
    1  version or file-presence check failed (see report)
    2  invalid command-line arguments (argparse)
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = repo_root / "data" / "processed"

# source key -> parquet stem
SOURCE_FILES = {
    "bb": "collected",
    "five_g": "lumos5g",
    "leo": "wetlinks",
}

EXPECTED_PYTHON = (3, 11)
CHUNK_SIZE = 1 << 20  # 1 MiB


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_files(data_root, hash_files=False):
    """Stat each expected parquet file; optionally hash it.

    "exists" reports actual path existence (any type, including empty
    regular files); "usable" is the success criterion: a regular,
    nonempty file. Directories and other non-regular paths never set
    "usable". Contents are never read except when --hash is set, and even
    then only as binary digest input, never parsed.
    """
    results = {}
    for source, stem in SOURCE_FILES.items():
        path = Path(data_root) / (stem + ".parquet")
        entry = {
            "path": str(path),
            "exists": False,
            "usable": False,
            "size_bytes": None,
        }
        try:
            if path.exists():
                entry["exists"] = True
                if path.is_file():
                    entry["size_bytes"] = path.stat().st_size
                    entry["usable"] = entry["size_bytes"] > 0
                    if hash_files:
                        entry["sha256"] = _sha256_file(path)
        except OSError as exc:
            entry["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            entry["exists"] = False
            entry["usable"] = False
        results[source] = entry
    return results


def build_report(data_root, hash_files=False):
    """Assemble the plain report object returned by this utility."""
    files = inspect_files(data_root, hash_files=hash_files)
    python_version_ok = sys.version_info[:2] == EXPECTED_PYTHON
    files_ok = all(
        entry["usable"] and "error" not in entry for entry in files.values()
    )
    return {
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "expected_python_version": "3.11",
        "python_version_ok": python_version_ok,
        "check_mode": "file_presence_only",
        "scientific_validity": "not_evaluated",
        "data_root": str(data_root),
        "source_files": dict(SOURCE_FILES),
        "files": files,
        "overall_ok": python_version_ok and files_ok,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preflight check: expected source parquet files present "
        "(file presence only; no content validation)."
    )
    parser.add_argument(
        "--data-root",
        default=None,
        metavar="PATH",
        help="data directory containing the parquet files "
        "(default: <repo>/data/processed, independent of cwd); "
        "a relative PATH is resolved against the current directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as a single JSON object (no other output)",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        dest="hash_files",
        help="also compute chunked sha256 of each file",
    )
    args = parser.parse_args(argv)

    data_root = (
        Path(args.data_root).expanduser()
        if args.data_root is not None
        else DEFAULT_DATA_ROOT
    )
    report = build_report(data_root, hash_files=args.hash_files)

    ok = report["overall_ok"]

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"python: {report['python_version']} (expected 3.11)")
        print(f"data_root: {report['data_root']}")
        print(f"check_mode: {report['check_mode']}")
        print(f"scientific_validity: {report['scientific_validity']}")
        for source, entry in report["files"].items():
            if "error" in entry:
                print(f"{source}: {entry['path']} ERROR {entry['error']['type']}")
            else:
                print(
                    f"{source}: {entry['path']} "
                    f"exists={entry['exists']} usable={entry['usable']} "
                    f"size={entry['size_bytes']}"
                )
        print(f"ok={str(ok).lower()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
