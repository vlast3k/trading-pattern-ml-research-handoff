#!/usr/bin/env python3
"""Download the approved budget-constrained 2025 Q1 Databento replication package."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
from dotenv import load_dotenv


REQUESTS = [
    {
        "name": "mnq_trades_2025q1",
        "schema": "trades",
        "symbols": ["MNQ.FUT"],
        "stype_in": "parent",
        "start": "2025-01-01",
        "end": "2025-04-01",
    },
    {
        "name": "mnq_nq_ohlcv_1m_2023_2026q1",
        "schema": "ohlcv-1m",
        "symbols": ["MNQ.FUT", "NQ.FUT"],
        "stype_in": "parent",
        "start": "2023-01-01",
        "end": "2026-04-01",
    },
    {
        "name": "mnq_nq_definitions_2023_2026q1",
        "schema": "definition",
        "symbols": ["MNQ.FUT", "NQ.FUT"],
        "stype_in": "parent",
        "start": "2023-01-01",
        "end": "2026-04-01",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=Path("data/databento_2025q1_replication")
    )
    parser.add_argument("--max-cost-usd", type=float, default=95.0)
    parser.add_argument("--poll-seconds", type=int, default=15)
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="ascii")


def main() -> None:
    args = parse_args()
    load_dotenv()
    if not os.getenv("DATABENTO_API_KEY"):
        raise SystemExit("DATABENTO_API_KEY is not set in the environment or .env")
    client = db.Historical()
    manifest_path = args.out / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    estimates = []
    total_cost = 0.0
    for request in REQUESTS:
        kwargs = {
            "dataset": "GLBX.MDP3",
            "schema": request["schema"],
            "symbols": request["symbols"],
            "stype_in": request["stype_in"],
            "start": request["start"],
            "end": request["end"],
        }
        cost = float(client.metadata.get_cost(**kwargs))
        size = int(client.metadata.get_billable_size(**kwargs))
        count = int(client.metadata.get_record_count(**kwargs))
        total_cost += cost
        estimates.append({**request, "cost_usd": cost, "billable_bytes": size, "record_count": count})
    if total_cost > args.max_cost_usd:
        raise SystemExit(
            f"Refusing to submit: estimated ${total_cost:.4f} exceeds "
            f"${args.max_cost_usd:.2f} ceiling"
        )
    manifest.update(
        {
            "dataset": "GLBX.MDP3",
            "approved_package": "2025_q1_recent_replication",
            "estimated_total_cost_usd": total_cost,
            "max_cost_usd": args.max_cost_usd,
            "requests": estimates,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    jobs = manifest.setdefault("jobs", {})
    write_json(manifest_path, manifest)

    for request in estimates:
        name = request["name"]
        if jobs.get(name, {}).get("job_id"):
            print(f"{name}: resuming {jobs[name]['job_id']}")
            continue
        job = client.batch.submit_job(
            dataset="GLBX.MDP3",
            schema=request["schema"],
            symbols=request["symbols"],
            stype_in=request["stype_in"],
            stype_out="instrument_id",
            start=request["start"],
            end=request["end"],
            encoding="dbn",
            compression="zstd",
            map_symbols=False,
            split_duration="month",
        )
        jobs[name] = {
            "job_id": job["id"],
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "submit_response": job,
        }
        write_json(manifest_path, manifest)
        print(f"{name}: submitted {job['id']}")

    pending = {item["name"] for item in estimates if not jobs.get(item["name"], {}).get("downloaded_files")}
    while pending:
        for name in list(pending):
            details = client.batch.get_job_details(jobs[name]["job_id"])
            jobs[name]["latest_details"] = details
            print(f"{name}: {details['state']}")
            if details["state"] == "done":
                files = client.batch.download(
                    jobs[name]["job_id"], output_dir=args.out / name
                )
                jobs[name]["downloaded_files"] = [str(path) for path in files]
                jobs[name]["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                pending.remove(name)
            elif details["state"] in {"expired", "failed"}:
                write_json(manifest_path, manifest)
                raise SystemExit(f"{name} ended in state {details['state']}")
            write_json(manifest_path, manifest)
        if pending:
            time.sleep(args.poll_seconds)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    print(f"Completed approved package under {args.out}")


if __name__ == "__main__":
    main()
