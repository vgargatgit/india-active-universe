#!/usr/bin/env python3
"""Write a compact GitHub Actions status report for release auditing."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from india_active_universe.profiles import DATA_RELEASE_MANIFEST_ARTIFACT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    release = Path(args.release)
    manifest = json.loads((release / DATA_RELEASE_MANIFEST_ARTIFACT).read_text(encoding="utf-8"))
    raw = subprocess.run(
        [
            "gh", "run", "view", args.run_id,
            "--json", "databaseId,headSha,status,conclusion,workflowName,url,createdAt,updatedAt,jobs",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    run = json.loads(raw)
    report = {
        "release_id": manifest.get("release_id"),
        "release_git_commit": manifest.get("git_commit"),
        "workflow_name": run.get("workflowName"),
        "run_id": run.get("databaseId"),
        "run_url": run.get("url"),
        "head_sha": run.get("headSha"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("createdAt"),
        "updated_at": run.get("updatedAt"),
        "jobs": [
            {
                "name": job.get("name"),
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
                "url": job.get("url"),
            }
            for job in run.get("jobs", [])
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"conclusion": report["conclusion"], "head_sha": report["head_sha"], "release_git_commit": report["release_git_commit"]}, sort_keys=True))


if __name__ == "__main__":
    main()
