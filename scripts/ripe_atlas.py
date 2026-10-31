"""RIPE Atlas helper (broadband calibration, proposal Section 11).

Reads the API key from RIPE_ATLAS_KEY (or .env in the repo root).

Usage:
    python scripts/ripe_atlas.py create-oneoff --target 94.103.167.15 \
        --probes 50 --description "sdwan broadband calibration"
    python scripts/ripe_atlas.py status --measurement-id 12345
    python scripts/ripe_atlas.py results --measurement-id 12345 \
        --out data/raw/ripe_atlas_results.json
"""

import argparse
import json
import os
import urllib.request


BASE = "https://atlas.ripe.net/api/v2"


def load_key() -> str:
    key = os.environ.get("RIPE_ATLAS_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("RIPE_ATLAS_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("RIPE_ATLAS_KEY not set (env var or .env)")


def request(method: str, path: str, payload: dict | None = None):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Key {load_key()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def cmd_create_oneoff(args: argparse.Namespace) -> None:
    payload = {
        "definitions": [
            {
                "type": "ping",
                "target": args.target,
                "description": args.description,
                "is_oneoff": True,
                "af": 4,
            }
        ],
        "probes": [{"requested": args.probes, "type": "area", "value": "WW"}],
        "is_oneoff": True,
    }
    result = request("POST", "/measurements/", payload)
    ids = result.get("measurements", [])
    print(json.dumps(result, indent=2))
    print("measurement ids:", ids)


def cmd_status(args: argparse.Namespace) -> None:
    result = request("GET", f"/measurements/{args.measurement_id}/")
    print("status:", result.get("status", {}).get("name"))
    print("probes participating:", len(result.get("probes", [])))


def cmd_results(args: argparse.Namespace) -> None:
    result = request("GET", f"/measurements/{args.measurement_id}/results/")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(result, fh)
    print(f"saved {len(result)} result rows -> {args.out}")


def cmd_public_results(args: argparse.Namespace) -> None:
    """Fetch results of a public measurement (no API key needed)."""
    path = f"/measurements/{args.measurement_id}/results/"
    params = []
    if args.start is not None:
        params.append(f"start={args.start}")
    if args.stop is not None:
        params.append(f"stop={args.stop}")
    params.append(f"page_size={args.page_size}")
    if params:
        path += "?" + "&".join(params)
    url = BASE + path
    with urllib.request.urlopen(url, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(result, fh)
    print(f"saved {len(result)} rows -> {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("create-oneoff")
    p1.add_argument("--target", required=True)
    p1.add_argument("--probes", type=int, default=50)
    p1.add_argument("--description", default="SD-WAN broadband calibration")
    p1.set_defaults(func=cmd_create_oneoff)

    p2 = sub.add_parser("status")
    p2.add_argument("--measurement-id", required=True)
    p2.set_defaults(func=cmd_status)

    p3 = sub.add_parser("results")
    p3.add_argument("--measurement-id", required=True)
    p3.add_argument("--out", required=True)
    p3.set_defaults(func=cmd_results)

    p4 = sub.add_parser("public-results")
    p4.add_argument("--measurement-id", required=True)
    p4.add_argument("--out", required=True)
    p4.add_argument("--start", type=int, default=None, help="unix start time")
    p4.add_argument("--stop", type=int, default=None, help="unix stop time")
    p4.add_argument("--page-size", type=int, default=5000)
    p4.set_defaults(func=cmd_public_results)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
