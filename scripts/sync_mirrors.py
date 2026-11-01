#!/usr/bin/env python3
"""Synchronize and audit ref parity between local Git, local-hub, and GitLab.

Agents are required to keep local Git (`local-hub` and local branches/tags) and
GitLab (`gitlab`) as equal representations while keeping GitHub (`origin`)
permanently retired. Non-main branch pushes to GitLab automatically include
`-o ci.skip` so mirroring branches never triggers CI pipeline storms during
the 30-day GitLab trial.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

RETIRED_HOST = "github.com"
DEFAULT_GITLAB_REMOTE = "gitlab"
DEFAULT_LOCAL_HUB_REMOTE = "local-hub"


class MirrorSyncError(RuntimeError):
    pass


def _git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=check,
    )


def local_refs(repo_dir: Path) -> dict[str, dict[str, str]]:
    """Return local branches and tags mapped to their object SHAs."""
    out = _git(repo_dir, "for-each-ref", "--format=%(refname) %(objectname)").stdout.splitlines()
    branches: dict[str, str] = {}
    tags: dict[str, str] = {}
    for line in out:
        ref, sha = line.split()
        if ref.startswith("refs/heads/"):
            branches[ref.removeprefix("refs/heads/")] = sha
        elif ref.startswith("refs/tags/"):
            tags[ref.removeprefix("refs/tags/")] = sha
    return {"branches": branches, "tags": tags}


def verify_remote_not_retired(repo_dir: Path, remote: str) -> str:
    """Refuse to push to a retired GitHub remote."""
    url = _git(repo_dir, "remote", "get-url", "--push", remote).stdout.strip()
    if RETIRED_HOST in url.lower() or "retired_github" in url.lower():
        raise MirrorSyncError(f"Refusing to push to retired GitHub remote {remote!r} ({url})")
    return url


def build_push_commands(
    *,
    remote: str,
    is_gitlab: bool,
    branches: list[str],
    include_tags: bool = True,
    ci_on_main: bool = False,
) -> list[list[str]]:
    """Construct safe git push commands that suppress CI on non-main branch syncs."""
    commands: list[list[str]] = []
    main_branches = [b for b in branches if b == "main"]
    topic_branches = [b for b in branches if b != "main"]

    if main_branches:
        cmd = ["git", "push"]
        if is_gitlab and not ci_on_main:
            cmd.extend(["-o", "ci.skip"])
        cmd.extend([remote, "refs/heads/main:refs/heads/main"])
        commands.append(cmd)

    if topic_branches:
        # Always pass -o ci.skip on topic/archive branch syncs to GitLab
        chunk_size = 25
        for idx in range(0, len(topic_branches), chunk_size):
            batch = topic_branches[idx : idx + chunk_size]
            cmd = ["git", "push"]
            if is_gitlab:
                cmd.extend(["-o", "ci.skip"])
            cmd.append(remote)
            cmd.extend(f"refs/heads/{b}:refs/heads/{b}" for b in batch)
            commands.append(cmd)

    if include_tags:
        cmd = ["git", "push"]
        if is_gitlab and not ci_on_main:
            cmd.extend(["-o", "ci.skip"])
        cmd.extend([remote, "--tags"])
        commands.append(cmd)

    return commands


def sync_mirrors(
    repo_dir: Path,
    *,
    remotes: tuple[str, ...] = (DEFAULT_LOCAL_HUB_REMOTE, DEFAULT_GITLAB_REMOTE),
    branches: list[str] | None = None,
    include_tags: bool = True,
    ci_on_main: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    refs = local_refs(repo_dir)
    selected_branches = sorted(branches if branches is not None else refs["branches"].keys())
    missing = [b for b in selected_branches if b not in refs["branches"]]
    if missing:
        raise MirrorSyncError(f"Requested branches do not exist locally: {missing}")

    results: dict[str, object] = {}
    for remote in remotes:
        url = verify_remote_not_retired(repo_dir, remote)
        is_gitlab = "gitlab" in url.lower() or remote == DEFAULT_GITLAB_REMOTE
        cmds = build_push_commands(
            remote=remote,
            is_gitlab=is_gitlab,
            branches=selected_branches,
            include_tags=include_tags,
            ci_on_main=ci_on_main,
        )
        if dry_run:
            results[remote] = {"url": url, "status": "dry_run", "commands": cmds}
            continue
        executed = []
        errors = []
        for cmd in cmds:
            proc = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
            executed.append({"command": cmd, "returncode": proc.returncode})
            if proc.returncode != 0:
                errors.append(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
                break
        results[remote] = {
            "url": url,
            "status": "ok" if not errors else "error",
            "commands_run": len(executed),
            "errors": errors,
        }

    return {
        "repo_dir": str(repo_dir),
        "head_main": refs["branches"].get("main"),
        "branch_count": len(selected_branches),
        "tag_count": len(refs["tags"]),
        "remotes": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--remotes", nargs="+", default=[DEFAULT_LOCAL_HUB_REMOTE, DEFAULT_GITLAB_REMOTE])
    parser.add_argument("--branch", action="append", dest="branches", help="Specific branch(es) to sync; default is all local branches")
    parser.add_argument("--no-tags", action="store_true", help="Skip pushing tags")
    parser.add_argument("--ci-on-main", action="store_true", help="Allow GitLab CI to trigger when pushing main")
    parser.add_argument("--dry-run", action="store_true", help="Print planned commands without executing git push")
    args = parser.parse_args(argv)
    try:
        receipt = sync_mirrors(
            args.repo_dir.resolve(),
            remotes=tuple(args.remotes),
            branches=args.branches,
            include_tags=not args.no_tags,
            ci_on_main=args.ci_on_main,
            dry_run=args.dry_run,
        )
    except MirrorSyncError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(receipt, indent=2))
    failed = any(
        isinstance(info, dict) and info.get("status") == "error"
        for info in receipt.get("remotes", {}).values()
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
