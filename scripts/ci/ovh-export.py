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


def verify(work, root, env):
    pipeline = decimal(env["CI_PIPELINE_ID"])
    sha = env["CI_COMMIT_SHA"]
    for name, filename in RECEIPTS.items():
        receipt = json.loads((work / "artifacts/receipts" / filename).read_text())
        job = str(receipt["job_id"])
        target = root / pipeline / decimal(job)
        meta = json.loads((target / "job.json").read_text())
        if (meta.get("schema") != "fdisbull-ovh-result-export-v1"
                or meta.get("source_commit") != sha or meta.get("pipeline_id") != pipeline
                or meta.get("job_id") != job or meta.get("job_name") != name
                or meta.get("export_success") is not True):
            raise ValueError("Required job result export is absent or differs")
        post = json.loads((target / "source-postcheck.json").read_text())
        if (post.get("source_commit") != sha or post.get("expected_source_commit") != sha
                or post.get("tracked_worktree_dirty") is not False or post.get("export_success") is not True):
            raise ValueError("Exported job source did not pass its postcheck")
        inventory = json.loads((target / "inventory.json").read_text())
        if not inventory or len(inventory) != meta.get("files"):
            raise ValueError("Missing or incomplete result inventory")
        seen = set()
        for entry in inventory:
            path = Path(entry["path"])
            if path.is_absolute() or ".." in path.parts or path.as_posix() in seen:
                raise ValueError("Unsafe/duplicate result inventory path")
            seen.add(path.as_posix())
            item = target / "exported" / path
            if any(p.is_symlink() for p in (item, *item.parents)):
                raise ValueError("Symlink in preserved results")
            if item.stat().st_size != entry["size"] or digest(item) != entry["sha256"]:
                raise ValueError("Preserved result changed")
        actual = {p.relative_to(target / "exported").as_posix()
                  for p in (target / "exported").rglob("*") if p.is_file()}
        if seen != actual:
            raise ValueError("Preserved files differ from the complete inventory")
        own_receipt = "artifacts/receipts/" + filename
        if own_receipt not in seen or digest(target / "exported" / own_receipt) != digest(work / own_receipt):
            raise ValueError("Canonical job receipt absent or different in preserved results")
        def references(value):
            if isinstance(value, dict):
                if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                    yield value
                for child in value.values():
                    yield from references(child)
            elif isinstance(value, list):
                for child in value:
                    yield from references(child)
        for reference in references(receipt):
            relative = reference_path(reference["path"], meta.get("project_directory", ""))
            if relative not in seen or digest(target / "exported" / relative) != reference["sha256"]:
                raise ValueError("A canonical job artifact is missing or differs in preserved results")
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
