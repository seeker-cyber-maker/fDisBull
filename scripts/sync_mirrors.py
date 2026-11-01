#!/usr/bin/env python3
"""Two-way synchronize and audit ref parity between local Git, local-hub, and GitLab.

Agents are required to keep local Git (`local-hub` and local branches/tags) and
GitLab (`gitlab`) as equal representations while keeping GitHub (`origin`)
permanently retired.

Key behaviors:
1. Fetches remote-tracking branches (`git fetch --no-tags <remote>`) first so
   any branch that exists only on GitLab or has newer commits on GitLab (such as
   `pr-local/56-miniplanets-display-20261031`) fast-forwards local `refs/heads/*`
   instead of failing with a non-fast-forward push rejection.
2. Preserves diverged branch tips on both sides under `refs/heads/<remote>-archive/*`
   and `refs/heads/local-archive/*` so zero commits are ever lost or overwritten.
3. Pushes only branches that are missing or behind on the remote, always passing
   `-o ci.skip` on topic/archive branches for GitLab so mirroring never triggers
   CI pipeline storms during the 30-day GitLab trial.
4. Continues across all branch batches and tags even if an individual ref fails,
   retrying failed batches per-ref so one ref never blocks the rest.
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


def _is_ancestor(repo_dir: Path, ancestor: str, descendant: str) -> bool:
    return _git(repo_dir, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def local_refs(repo_dir: Path, remote: str | None = None) -> dict[str, dict[str, str]]:
    """Return local branches, tags, and optional remote-tracking branches mapped to SHAs."""
    out = _git(repo_dir, "for-each-ref", "--format=%(refname) %(objectname)").stdout.splitlines()
    branches: dict[str, str] = {}
    tags: dict[str, str] = {}
    remote_branches: dict[str, str] = {}
    remote_prefix = f"refs/remotes/{remote}/" if remote else None
    for line in out:
        ref, sha = line.split()
        if ref.startswith("refs/heads/"):
            branches[ref.removeprefix("refs/heads/")] = sha
        elif ref.startswith("refs/tags/"):
            tags[ref.removeprefix("refs/tags/")] = sha
        elif remote_prefix and ref.startswith(remote_prefix):
            name = ref.removeprefix(remote_prefix)
            if name != "HEAD":
                remote_branches[name] = sha
    return {"branches": branches, "tags": tags, "remote_branches": remote_branches}


def verify_remote_not_retired(repo_dir: Path, remote: str) -> str:
    """Refuse to push to a retired GitHub remote."""
    url = _git(repo_dir, "remote", "get-url", "--push", remote).stdout.strip()
    if RETIRED_HOST in url.lower() or "retired_github" in url.lower():
        raise MirrorSyncError(f"Refusing to push to retired GitHub remote {remote!r} ({url})")
    return url


def reconcile_with_remote(
    repo_dir: Path,
    remote: str,
    *,
    selected_branches: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Reconcile local refs/heads/* with refs/remotes/<remote>/* before pushing."""
    snapshot = local_refs(repo_dir, remote)
    local_b = snapshot["branches"]
    remote_b = snapshot["remote_branches"]

    already_synced: list[str] = []
    to_push: list[str] = []
    fast_forwarded_local: list[str] = []
    imported_from_remote: list[str] = []
    diverged_archived: list[str] = []

    # 1. Import any branch present on remote that does not exist in local refs/heads/*
    if selected_branches is None:
        for r_name, r_sha in sorted(remote_b.items()):
            if r_name not in local_b:
                if not dry_run:
                    _git(repo_dir, "update-ref", f"refs/heads/{r_name}", r_sha)
                    local_b[r_name] = r_sha
                imported_from_remote.append(r_name)
                already_synced.append(r_name)

    target_branches = sorted(selected_branches if selected_branches is not None else local_b.keys())
    for b in target_branches:
        if b in imported_from_remote:
            continue
        l_sha = local_b.get(b)
        if not l_sha:
            raise MirrorSyncError(f"Requested branch does not exist locally: {b}")
        r_sha = remote_b.get(b)
        if r_sha is None:
            to_push.append(b)
        elif l_sha == r_sha:
            already_synced.append(b)
        elif _is_ancestor(repo_dir, r_sha, l_sha):
            # Local is strictly ahead of remote -> push to remote
            to_push.append(b)
        elif _is_ancestor(repo_dir, l_sha, r_sha):
            # Remote is strictly ahead of local -> fast-forward local ref!
            if not dry_run:
                _git(repo_dir, "update-ref", f"refs/heads/{b}", r_sha)
            fast_forwarded_local.append(b)
        else:
            # Diverged: preserve local tip under local-archive/<b>, fast-forward <b> to remote tip
            arch_local = f"local-archive/{b}"
            if not dry_run:
                _git(repo_dir, "update-ref", f"refs/heads/{arch_local}", l_sha)
                _git(repo_dir, "update-ref", f"refs/heads/{b}", r_sha)
            diverged_archived.append(b)
            if remote_b.get(arch_local) != l_sha:
                to_push.append(arch_local)

    return {
        "already_synced": already_synced,
        "to_push": to_push,
        "fast_forwarded_local": fast_forwarded_local,
        "imported_from_remote": imported_from_remote,
        "diverged_archived": diverged_archived,
    }


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
    results: dict[str, object] = {}
    for remote in remotes:
        url = verify_remote_not_retired(repo_dir, remote)
        is_gitlab = "gitlab" in url.lower() or remote == DEFAULT_GITLAB_REMOTE

        fetch_ok = True
        fetch_error = None
        if not dry_run:
            # Fetch remote branches & tags first so local knows what is ahead/behind on remote
            f_proc = _git(repo_dir, "fetch", "--tags", remote, check=False)
            if f_proc.returncode != 0:
                # Retry without --tags in case a tag collides
                f_proc2 = _git(repo_dir, "fetch", "--no-tags", remote, check=False)
                fetch_ok = f_proc2.returncode == 0
                if not fetch_ok:
                    fetch_error = (f_proc2.stderr or f_proc.stderr).strip()

        plan = reconcile_with_remote(
            repo_dir,
            remote,
            selected_branches=branches,
            dry_run=dry_run,
        )
        cmds = build_push_commands(
            remote=remote,
            is_gitlab=is_gitlab,
            branches=plan["to_push"],
            include_tags=include_tags,
            ci_on_main=ci_on_main,
        )
        if dry_run:
            results[remote] = {
                "url": url,
                "status": "dry_run",
                "already_synced_count": len(plan["already_synced"]),
                "to_push_count": len(plan["to_push"]),
                "fast_forwarded_local": plan["fast_forwarded_local"],
                "imported_from_remote": plan["imported_from_remote"],
                "diverged_archived": plan["diverged_archived"],
                "commands": cmds,
            }
            continue

        executed = []
        errors = []
        for cmd in cmds:
            proc = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
            executed.append({"command": cmd, "returncode": proc.returncode})
            if proc.returncode != 0:
                # If a multi-branch batch failed, retry each refspec individually so one ref never blocks others
                refspecs = [arg for arg in cmd if arg.startswith("refs/heads/")]
                if len(refspecs) > 1:
                    prefix = [arg for arg in cmd if not arg.startswith("refs/heads/")]
                    for spec in refspecs:
                        sub = subprocess.run([*prefix, spec], cwd=repo_dir, capture_output=True, text=True)
                        if sub.returncode != 0:
                            # Re-fetch and reconcile that single branch in case remote advanced concurrently
                            b_name = spec.split(":", 1)[0].removeprefix("refs/heads/")
                            _git(repo_dir, "fetch", "--no-tags", remote, f"refs/heads/{b_name}:refs/remotes/{remote}/{b_name}", check=False)
                            sub_plan = reconcile_with_remote(repo_dir, remote, selected_branches=[b_name], dry_run=False)
                            if sub_plan["fast_forwarded_local"] or sub_plan["diverged_archived"]:
                                plan["fast_forwarded_local"].extend(sub_plan["fast_forwarded_local"])
                                plan["diverged_archived"].extend(sub_plan["diverged_archived"])
                                for arch_b in sub_plan["to_push"]:
                                    subprocess.run([*prefix, f"refs/heads/{arch_b}:refs/heads/{arch_b}"], cwd=repo_dir, capture_output=True, text=True)
                            else:
                                errors.append(f"{b_name}: {(sub.stderr or sub.stdout).strip()}")
                else:
                    errors.append((proc.stderr or proc.stdout).strip() or f"exit {proc.returncode}")

        results[remote] = {
            "url": url,
            "fetch_ok": fetch_ok,
            "fetch_error": fetch_error,
            "status": "ok" if not errors else "partial_or_error",
            "already_synced_count": len(plan["already_synced"]),
            "pushed_branch_count": len(plan["to_push"]),
            "fast_forwarded_local": plan["fast_forwarded_local"],
            "imported_from_remote": plan["imported_from_remote"],
            "diverged_archived": plan["diverged_archived"],
            "commands_run": len(executed),
            "errors": errors,
        }

    final_refs = local_refs(repo_dir)
    return {
        "repo_dir": str(repo_dir),
        "head_main": final_refs["branches"].get("main"),
        "branch_count": len(final_refs["branches"]),
        "tag_count": len(final_refs["tags"]),
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
        isinstance(info, dict) and info.get("status") not in ("ok", "dry_run")
        for info in receipt.get("remotes", {}).values()
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
