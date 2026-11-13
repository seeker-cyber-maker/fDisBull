#!/usr/bin/env python3
"""Preserve selected CI results on OVH independently of GitLab artifact expiry."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re

RECEIPTS = {"test-and-package": "ordinary.json",
            "native-debugger-stable": "native-stable.json",
            "native-debugger-layers": "native-layers.json",
            "native-unified": "native-unified.json"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def decimal(value):
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError("Invalid CI pipeline/job identity")
    return value


def reference_path(value, project_directory):
    if (not isinstance(value, str) or not value or '..' in PurePosixPath(value).parts
            or str(PurePosixPath(value)) != value):
        raise ValueError('Unsafe artifact reference')
    path = PurePosixPath(value)
    base = PurePosixPath(project_directory)
    if not base.is_absolute() or '..' in base.parts or str(base) != project_directory:
        raise ValueError('Invalid producer project directory')
    if path.is_absolute():
        try:
            path = path.relative_to(base)
        except ValueError as exc:
            raise ValueError('Artifact reference outside producer project') from exc
    if str(path) in ('', '.'):
        raise ValueError('Invalid artifact reference')
    return str(path)


def export(work, root, env):
    work = work.resolve()
    sha = env["CI_COMMIT_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid source identity")
    target = root / decimal(env["CI_PIPELINE_ID"]) / decimal(env["CI_JOB_ID"])
    if target.exists() or target.is_symlink():
        raise ValueError("Preserve the earlier export; do not overwrite it")
    target.mkdir(parents=True)
    record = {"schema": "fdisbull-ovh-result-export-v1", "source_commit": sha,
              "pipeline_id": env["CI_PIPELINE_ID"], "job_id": env["CI_JOB_ID"],
              "job_name": env["CI_JOB_NAME"], "job_status": env.get("CI_JOB_STATUS"),
              "project_directory": str(work),
              "export_success": False}
    try:
        path = Path(__file__).with_name("export-local-artifacts.py")
        spec = importlib.util.spec_from_file_location("ci_result_export", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.SELECTIONS += (".native/pe/qemu-9.2.4/pc-bios/**/*",)
        module.export(work, target / "exported", sha)
        inventory = []
        for item in sorted((target / "exported").rglob("*")):
            if item.is_symlink():
                raise ValueError("Symlink in exported results")
            if item.is_file():
                relative = item.relative_to(target / "exported").as_posix()
                original = work / relative
                sha256 = digest(item)
                if item.stat().st_size != original.stat().st_size or sha256 != digest(original):
                    raise ValueError("Host export differs from the original result")
                inventory.append({"path": relative, "size": item.stat().st_size, "sha256": sha256})
        with (target / "inventory.json").open("x") as stream:
            json.dump(inventory, stream, indent=2)
            stream.write("\n")
        record["export_success"] = True
        record["files"] = len(inventory)
    except Exception as error:
        record["error_type"] = type(error).__name__
        raise
    finally:
        record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (target / "job.json").open("x") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield value
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def verify_job_export(root, pipeline_id, job_id, expected_sha, expected_job_name,
                      *, expected_job_status, required_receipt=None):
    """Verify preserved bytes for one completed job, without qualifying its outcome.

    required_receipt, when supplied, is the canonical producer receipt path in
    the caller's worktree. It is compared byte-for-byte and its references are
    verified against the preserved inventory.
    """
    pipeline, job = decimal(pipeline_id), decimal(job_id)
    if (not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha)
            or not isinstance(expected_job_name, str) or not expected_job_name
            or expected_job_status not in {"success", "failed", "canceled"}):
        raise ValueError("Invalid expected job identity or terminal status")
    target = Path(root) / pipeline / job
    meta = json.loads((target / "job.json").read_text())
    if (meta.get("schema") != "fdisbull-ovh-result-export-v1"
            or meta.get("source_commit") != expected_sha or meta.get("pipeline_id") != pipeline
            or meta.get("job_id") != job or meta.get("job_name") != expected_job_name
            or meta.get("job_status") != expected_job_status or meta.get("export_success") is not True):
        raise ValueError("Required job result export is absent or differs")
    post = json.loads((target / "source-postcheck.json").read_text())
    if (post.get("source_commit") != expected_sha or post.get("expected_source_commit") != expected_sha
            or post.get("tracked_worktree_dirty") is not False or post.get("export_success") is not True):
        raise ValueError("Exported job source did not pass its postcheck")
    inventory = json.loads((target / "inventory.json").read_text())
    if not isinstance(inventory, list) or not inventory or len(inventory) != meta.get("files"):
        raise ValueError("Missing or incomplete result inventory")
    seen = set()
    for entry in inventory:
        raw = entry["path"]
        path = Path(raw)
        if (not isinstance(raw, str) or not raw or path.is_absolute() or ".." in path.parts
                or path.as_posix() != raw or raw in seen):
            raise ValueError("Unsafe/duplicate result inventory path")
        seen.add(raw)
        item = target / "exported" / path
        if any(p.is_symlink() for p in (item, *item.parents)):
            raise ValueError("Symlink in preserved results")
        if item.stat().st_size != entry["size"] or digest(item) != entry["sha256"]:
            raise ValueError("Preserved result changed")
    exported = target / "exported"
    paths = list(exported.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("Symlink in preserved results")
    actual = {p.relative_to(exported).as_posix() for p in paths if p.is_file()}
    if seen != actual:
        raise ValueError("Preserved files differ from the complete inventory")
    if required_receipt is not None:
        canonical = Path(required_receipt)
        own_receipt = "artifacts/receipts/" + canonical.name
        if own_receipt not in seen or digest(exported / own_receipt) != digest(canonical):
            raise ValueError("Canonical job receipt absent or different in preserved results")
        receipt = json.loads(canonical.read_text())
        if str(receipt.get("job_id")) != job:
            raise ValueError("Canonical job receipt identity differs")
        for reference in references(receipt):
            relative = reference_path(reference["path"], meta.get("project_directory", ""))
            if relative not in seen or digest(exported / relative) != reference["sha256"]:
                raise ValueError("A canonical job artifact is missing or differs in preserved results")
    return {"status": "export-verified", "pipeline_id": pipeline, "job_id": job,
            "source_commit": expected_sha, "job_name": expected_job_name,
            "job_status": expected_job_status}


def verify(work, root, env):
    pipeline = decimal(env["CI_PIPELINE_ID"])
    sha = env["CI_COMMIT_SHA"]
    for name, filename in RECEIPTS.items():
        canonical = work / "artifacts/receipts" / filename
        receipt = json.loads(canonical.read_text())
        verify_job_export(root, pipeline, str(receipt["job_id"]), sha, name,
                          expected_job_status="success", required_receipt=canonical)
    print("All four ordinary/native job exports verified on OVH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "verify"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "export":
        export(args.work.resolve(), args.root.resolve(), os.environ)
    else:
        verify(args.work.resolve(), args.root.resolve(), os.environ)


if __name__ == "__main__":
    main()
