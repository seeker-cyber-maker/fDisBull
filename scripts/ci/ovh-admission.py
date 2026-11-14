#!/usr/bin/env python3
"""Record OVH CI storage telemetry without reserve-based admission."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil


def observe(path, expected, reserve=20_000_000_000):
    if expected < 0 or reserve < 0:
        raise ValueError("Invalid allocation estimate or reserve telemetry")
    free = shutil.disk_usage(path).free
    return {"free_bytes": free, "expected_bytes": expected, "reserve_bytes": reserve,
            "storage_status": "observed", "reserve_enforced": False}


def main():
    tags = json.loads(os.environ.get("CI_RUNNER_TAGS", "[]"))
    if "fdisbull-ovh-ca" not in tags or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Require the dedicated OVH Linux x86_64 runner")
    job = os.environ["CI_JOB_ID"]
    if not job.isdecimal():
        raise ValueError("Invalid job identity")
    result = observe(Path.cwd(), int(os.environ["FDISBULL_EXPECTED_BYTES"]))
    result.update(source_commit=os.environ["CI_COMMIT_SHA"], job_id=job,
                  pipeline_id=os.environ["CI_PIPELINE_ID"], runner_id=os.environ["CI_RUNNER_ID"],
                  observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    path = Path("artifacts/receipts") / f"ovh-admission-{job}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
