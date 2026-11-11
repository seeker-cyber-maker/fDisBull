#!/usr/bin/env python3
"""Bounded, fast-forward-only local-hub/GitLab mirror worker.

This module is intentionally invoked by an external scheduler.  It does not
install hooks, create launch agents, read credentials, or start itself.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

SCHEMA = "fdisbull-mirror-sync-1"
MARKER_NAME = ".fdisbull-mirror-cache.json"
REF_NS = "refs/mirror-sync/source"
FETCH_NS = "refs/mirror-sync/fetch"
ARCHIVE_NS = "refs/mirror-sync/archive"
OID_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
BAD_REF_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")


class WorkerError(Exception):
    def __init__(self, message: str, *, code: int = 1):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, value: object, *, create_parent: bool = True) -> None:
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.is_dir():
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    try:
        with tmp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        try:
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerError(f"cannot read JSON config/state: {path.name}", code=2) from exc
    if not isinstance(value, dict):
        raise WorkerError(f"expected a JSON object: {path.name}", code=2)
    return value


def _clean_git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GCM_INTERACTIVE": "never",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_SSH_COMMAND": "ssh -oBatchMode=yes -oNumberOfPasswordPrompts=0",
    })
    return env


class Git:
    def __init__(self, executable: str, cache: Path, deadline: float, command_timeout: int):
        self.executable = executable
        self.cache = cache
        self.deadline = deadline
        self.command_timeout = command_timeout
        self.env = _clean_git_env()

    def run(self, *args: str, cwd: Path | None = None, check: bool = True,
            input_data: str | None = None) -> str:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerError("run deadline exceeded")
        timeout = min(float(self.command_timeout), remaining)
        try:
            result = subprocess.run(
                [self.executable, *args], cwd=str(cwd or self.cache), env=self.env,
                capture_output=True, text=True, input=input_data, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"git command timed out ({args[0] if args else 'unknown'})") from exc
        except OSError as exc:
            raise WorkerError(f"git command could not start ({args[0] if args else 'unknown'})") from exc
        if check and result.returncode:
            # Do not retain or print remote stderr; it can contain transport details.
            raise WorkerError(f"git command failed ({args[0] if args else 'unknown'}, exit {result.returncode})")
        return result.stdout.strip()


def _safe_url_identity(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password:
        raise WorkerError("gitlab URL must not embed credentials", code=2)
    return hashlib.sha256(url.encode()).hexdigest()


def _load_config(path: Path) -> dict:
    cfg = _read_json(path)
    required = {
        "format", "git", "hub", "gitlab", "cache", "state_dir", "volumes",
        "command_timeout_s", "run_timeout_s",
    }
    if set(cfg) != required or cfg.get("format") != SCHEMA:
        raise WorkerError("config keys or schema do not match fdisbull-mirror-sync-1", code=2)
    for key in ("git", "hub", "cache", "state_dir"):
        if not isinstance(cfg[key], str) or not Path(cfg[key]).is_absolute():
            raise WorkerError(f"config {key} must be an absolute path", code=2)
    if not isinstance(cfg["gitlab"], str):
        raise WorkerError("config gitlab must be a remote URL", code=2)
    parsed = urlsplit(cfg["gitlab"])
    if not (parsed.scheme in {"https", "ssh", "git"} and parsed.netloc) and not Path(cfg["gitlab"]).is_absolute():
        raise WorkerError("gitlab must be an exact supported remote URL", code=2)
    _safe_url_identity(cfg["gitlab"])
    if not isinstance(cfg["volumes"], list):
        raise WorkerError("volumes must be a list", code=2)
    for row in cfg["volumes"]:
        if not isinstance(row, dict) or set(row) != {"path", "uuid"}:
            raise WorkerError("each volume requires path and uuid", code=2)
        if not isinstance(row["path"], str) or not Path(row["path"]).is_absolute():
            raise WorkerError("volume path must be absolute", code=2)
        if not isinstance(row["uuid"], str) or not row["uuid"]:
            raise WorkerError("volume uuid must be nonempty", code=2)
    for key in ("command_timeout_s", "run_timeout_s"):
        if not isinstance(cfg[key], int) or isinstance(cfg[key], bool) or cfg[key] < 1:
            raise WorkerError(f"{key} must be a positive integer", code=2)
    if cfg["command_timeout_s"] > 45 or cfg["run_timeout_s"] > 55:
        raise WorkerError("timeouts exceed the service bounds (45s command, 55s run)", code=2)
    return cfg


def _validate_volumes(cfg: dict, deadline: float) -> None:
    # Empty volume lists are supported for isolated fake-repository integration tests.
    for row in cfg["volumes"]:
        mount = Path(row["path"])
        if not mount.exists() or not os.path.ismount(mount):
            raise WorkerError(f"expected mounted volume is unavailable: {mount}", code=2)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerError("run deadline exceeded during volume validation")
        try:
            raw = subprocess.run(
                ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
                capture_output=True, timeout=min(5.0, remaining), check=False,
            )
            info = plistlib.loads(raw.stdout) if raw.returncode == 0 else {}
        except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException):
            info = {}
        actual_mount = info.get("MountPoint")
        actual_uuid = info.get("VolumeUUID")
        if actual_mount != str(mount) or str(actual_uuid).lower() != row["uuid"].lower():
            raise WorkerError(f"mounted volume identity mismatch: {mount}", code=2)


def _identity(cfg: dict) -> dict:
    return {
        "schema": SCHEMA,
        "git": str(Path(cfg["git"]).resolve()),
        "hub": str(Path(cfg["hub"]).resolve()),
        "gitlab_sha256": _safe_url_identity(cfg["gitlab"]),
        "cache": str(Path(cfg["cache"]).resolve()),
        "state_dir": str(Path(cfg["state_dir"]).resolve()),
        "volumes": sorted(
            [{"path": os.path.realpath(v["path"]), "uuid": v["uuid"].lower()} for v in cfg["volumes"]],
            key=lambda x: x["path"],
        ),
    }


def _git_direct(executable: str, *args: str, cwd: Path | None = None,
                deadline: float | None = None) -> str:
    remaining = 10.0 if deadline is None else min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise WorkerError("run deadline exceeded during Git preflight")
    try:
        result = subprocess.run(
            [executable, *args], cwd=str(cwd) if cwd else None, env=_clean_git_env(),
            capture_output=True, text=True, timeout=remaining, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerError("local Git preflight failed", code=2) from exc
    if result.returncode:
        raise WorkerError("local Git preflight failed", code=2)
    return result.stdout.strip()


def _validate_local_repositories(cfg: dict, executable: str, deadline: float) -> None:
    git_path = Path(executable)
    if not git_path.is_absolute() or not git_path.is_file() or not os.access(git_path, os.X_OK):
        raise WorkerError("git must be an absolute executable path", code=2)
    hub = Path(cfg["hub"])
    if not hub.exists() or _git_direct(executable, "--git-dir", str(hub), "rev-parse", "--is-bare-repository",
                                       deadline=deadline) != "true":
        raise WorkerError("hub must be an existing bare Git repository", code=2)


def _parse_ls_remote(text: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            oid, ref = line.split("\t", 1)
        except ValueError as exc:
            raise WorkerError("unexpected ls-remote response") from exc
        if ref.endswith("^{}"):
            continue
        if not (ref.startswith("refs/heads/") or ref.startswith("refs/tags/")):
            continue
        if not OID_RE.fullmatch(oid):
            raise WorkerError("remote advertises a malformed branch or tag object ID")
        name = ref.split("/", 2)[2]
        parts = name.split("/")
        if (not name or BAD_REF_CHARS.search(ref) or ".." in ref or "@{" in ref
                or ref.endswith("/") or ref.startswith("/") or "//" in ref
                or any(part.startswith(".") or part.endswith(".") or part.endswith(".lock")
                       for part in parts)):
            raise WorkerError("remote advertises an unsupported branch or tag ref")
        if ref in refs and refs[ref] != oid.lower():
            raise WorkerError("duplicate ref in remote snapshot")
        refs[ref] = oid.lower()
    return refs


def _snapshot(git: Git, side: str, remote: str, run_id: str) -> dict[str, str]:
    live = _parse_ls_remote(git.run("ls-remote", "--refs", remote))
    if not live:
        # Empty repositories are valid; distinguish them from a failed command (raised above).
        return {}
    specs = []
    for ref in sorted(live):
        dest = f"{FETCH_NS}/{run_id}/{side}/{ref.removeprefix('refs/')}"
        specs.append(f"+{ref}:{dest}")
    git.run("fetch", "--no-tags", "--no-write-fetch-head", remote, *specs)
    fetched: dict[str, str] = {}
    prefix = f"{FETCH_NS}/{run_id}/{side}/"
    for line in git.run("for-each-ref", "--format=%(refname) %(objectname)", prefix).splitlines():
        dest, got = line.split()
        ref = "refs/" + dest.removeprefix(prefix)
        fetched[ref] = got.lower()
    if fetched != live:
        raise WorkerError(f"remote snapshot changed during fetch ({side})")
    return fetched


def _ref_oid(git: Git, ref: str) -> str | None:
    out = git.run("rev-parse", "--verify", "--quiet", ref, check=False)
    return out.lower() if out else None


def _archive_observed_remote_tip(git: Git, remote: str, side: str, ref: str,
                                 oid: str, run_id: str) -> None:
    """Fetch and archive a newly observed tip before treating readback as complete."""
    temp = f"{FETCH_NS}/{run_id}/verify/{side}/{ref.removeprefix('refs/')}"
    git.run("fetch", "--no-tags", "--no-write-fetch-head", remote, f"+{ref}:{temp}")
    fetched = git.run("rev-parse", "--verify", temp).lower()
    if fetched != oid:
        raise WorkerError(f"remote ref changed while archiving readback ({side})")
    archive_ref = f"{ARCHIVE_NS}/{oid[:2]}/{oid}"
    old_archive = _ref_oid(git, archive_ref)
    if old_archive is None:
        git.run("update-ref", archive_ref, oid, "0" * len(oid))
    elif old_archive != oid:
        raise WorkerError("immutable archive ref collision")


def _update_source_tracking(git: Git, side: str, ref: str, oid: str) -> None:
    source_ref = f"{REF_NS}/{side}/{ref.removeprefix('refs/')}"
    old_source = _ref_oid(git, source_ref)
    if old_source != oid:
        git.run("update-ref", source_ref, oid, old_source or ("0" * len(oid)))


def _update_source_refs(git: Git, state: dict, snapshots: dict[str, dict[str, str]], run_id: str) -> None:
    # Batch all references: the live repositories contain hundreds of refs.
    existing_sources: dict[str, str] = {}
    for side in ("hub", "gitlab"):
        prefix = f"{REF_NS}/{side}"
        for line in git.run("for-each-ref", "--format=%(refname) %(objectname)", prefix).splitlines():
            name, oid = line.split()
            existing_sources[name] = oid.lower()
    existing_archive: dict[str, str] = {}
    for line in git.run("for-each-ref", "--format=%(refname) %(objectname)", ARCHIVE_NS).splitlines():
        name, oid = line.split()
        existing_archive[name] = oid.lower()
    archive_oids: set[str] = set(existing_sources.values())
    for side in ("hub", "gitlab"):
        for rec in state["seen"][side].values():
            oid = rec.get("last_oid")
            if oid:
                archive_oids.add(oid.lower())
        archive_oids.update(oid.lower() for oid in snapshots[side].values())
    archive_commands = ["start"]
    for oid in sorted(archive_oids):
        archive_ref = f"{ARCHIVE_NS}/{oid[:2]}/{oid}"
        old = existing_archive.get(archive_ref)
        if old and old != oid:
            raise WorkerError("immutable archive ref collision")
        if old is None:
            archive_commands.append(f"create {archive_ref} {oid}")
    if len(archive_commands) > 1:
        archive_commands.extend(["prepare", "commit"])
        git.run("update-ref", "--stdin", input_data="\n".join(archive_commands) + "\n")

    # Only after archive refs commit may live source refs move.
    source_commands = ["start"]
    for side in ("hub", "gitlab"):
        desired = {
            f"{REF_NS}/{side}/{ref.removeprefix('refs/')}" : oid
            for ref, oid in snapshots[side].items()
        }
        prefix = f"{REF_NS}/{side}/"
        for old in [name for name in existing_sources if name.startswith(prefix)]:
            if old not in desired:
                source_commands.append(f"delete {old} {existing_sources[old]}")
        for ref, oid in desired.items():
            old_oid = existing_sources.get(ref)
            if old_oid != oid:
                if old_oid is None:
                    source_commands.append(f"create {ref} {oid}")
                else:
                    source_commands.append(f"update {ref} {oid} {old_oid}")
    if len(source_commands) > 1:
        source_commands.extend(["prepare", "commit"])
        git.run("update-ref", "--stdin", input_data="\n".join(source_commands) + "\n")

    temp_prefix = f"{FETCH_NS}/{run_id}/"
    temp_refs = git.run("for-each-ref", "--format=%(refname)", temp_prefix).splitlines()
    if temp_refs:
        cleanup = ["start", *(f"delete {ref}" for ref in temp_refs), "prepare", "commit"]
        git.run("update-ref", "--stdin", input_data="\n".join(cleanup) + "\n")


def _advance_seen(state: dict, snapshots: dict[str, dict[str, str]], *, update_oids: bool = True) -> list[dict]:
    holds = []
    for side in ("hub", "gitlab"):
        seen = state["seen"][side]
        current = snapshots[side]
        for ref, rec in list(seen.items()):
            if rec.get("state") == "present" and ref not in current:
                rec["state"] = "deleted"
                rec["deleted_at"] = _now()
                holds.append({"ref": ref, "reason": "observed-deletion", "side": side})
            elif rec.get("state") == "deleted" and ref in current:
                holds.append({"ref": ref, "reason": "deleted-ref-reappeared", "side": side})
            elif rec.get("state") == "pending_create":
                if ref not in current:
                    rec["state"] = "deleted"
                    rec["deleted_at"] = _now()
                    holds.append({"ref": ref, "reason": "unconfirmed-create-disappeared", "side": side})
                elif current[ref] != rec.get("pending_oid"):
                    rec["state"] = "conflict"
                    rec["observed_oid"] = current[ref]
                    rec["conflicted_at"] = _now()
                    holds.append({"ref": ref, "reason": "unconfirmed-create-conflict", "side": side})
                else:
                    rec["state"] = "present"
                    rec["last_oid"] = current[ref]
                    rec.pop("pending_oid", None)
                    rec["confirmed_at"] = _now()
            elif rec.get("state") == "conflict":
                holds.append({"ref": ref, "reason": "pending-create-conflict", "side": side})
        for ref, oid in current.items():
            if ref not in seen:
                if update_oids:
                    seen[ref] = {"state": "present", "last_oid": oid, "first_seen_at": _now()}
            elif update_oids and seen[ref].get("state") == "present":
                seen[ref]["last_oid"] = oid
    return holds


def _record_pending_create(state: dict, side: str, ref: str, oid: str) -> None:
    state["seen"][side][ref] = {"state": "pending_create", "pending_oid": oid,
                                 "first_seen_at": _now()}


def _confirm_created_ref(state: dict, side: str, ref: str, oid: str) -> None:
    state["seen"][side][ref] = {"state": "present", "last_oid": oid,
                                 "first_seen_at": state["seen"][side].get(ref, {}).get("first_seen_at", _now()),
                                 "confirmed_at": _now()}


def _mark_ref_conflict(state: dict, side: str, ref: str, oid: str | None) -> None:
    state["seen"][side][ref] = {"state": "conflict", "observed_oid": oid,
                                 "first_seen_at": state["seen"][side].get(ref, {}).get("first_seen_at", _now())}


def _is_ancestor(git: Git, a: str, b: str) -> bool:
    # Git.run returns stdout only; inspect the command status directly for this predicate.
    remaining = git.deadline - time.monotonic()
    if remaining <= 0:
        raise WorkerError("run deadline exceeded")
    try:
        result = subprocess.run(
            [git.executable, "merge-base", "--is-ancestor", a, b], cwd=str(git.cache),
            env=git.env, capture_output=True, text=True,
            timeout=min(float(git.command_timeout), remaining), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerError("git ancestry check failed") from exc
    if result.returncode not in (0, 1):
        raise WorkerError("git ancestry check failed")
    return result.returncode == 0


def _checked_out_branches(git: Git, hub: Path) -> set[str]:
    text = git.run("--git-dir", str(hub), "worktree", "list", "--porcelain")
    return {line.removeprefix("branch refs/heads/") for line in text.splitlines()
            if line.startswith("branch refs/heads/")}


def _push(git: Git, side: str, remote: str, source_side: str, ref: str, oid: str) -> None:
    source_ref = f"{REF_NS}/{source_side}/{ref.removeprefix('refs/') }"
    if _ref_oid(git, source_ref) != oid:
        raise WorkerError("source ref changed before push")
    args = ["-c", "push.followTags=false", "-c", "push.recurseSubmodules=no", "push"]
    if side == "gitlab":
        args.extend(["-o", "ci.skip"])
    args.extend([remote, f"{source_ref}:{ref}"])
    git.run(*args)


def _sync_refs(git: Git, cfg: dict, state: dict, state_path: Path,
               snapshots: dict[str, dict[str, str]], deletion_holds: list[dict],
               run_id: str) -> tuple[list[dict], list[dict]]:
    actions: list[dict] = []
    holds = list(deletion_holds)
    tombstoned = {
        side: {ref for ref, rec in state["seen"][side].items()
               if rec.get("state") in {"deleted", "conflict"}}
        for side in ("hub", "gitlab")
    }
    all_refs = sorted(set(snapshots["hub"]) | set(snapshots["gitlab"]) |
                      set(state["seen"]["hub"]) | set(state["seen"]["gitlab"]))
    for ref in all_refs:
        if ref in tombstoned["hub"] or ref in tombstoned["gitlab"]:
            # Deletion/recreation is a human decision; never resurrect automatically.
            if ref in snapshots["hub"] or ref in snapshots["gitlab"]:
                holds.append({"ref": ref, "reason": "deletion-tombstone"})
            continue
        left, right = snapshots["hub"].get(ref), snapshots["gitlab"].get(ref)
        if left == right:
            continue
        if ref.startswith("refs/tags/") and left is not None and right is not None:
            holds.append({"ref": ref, "reason": "tag-mismatch"})
            continue
        if left is None and right is None:
            continue
        if left is None:
            src_side, dst_side, src_oid, dst_oid = "gitlab", "hub", right, None
        elif right is None:
            src_side, dst_side, src_oid, dst_oid = "hub", "gitlab", left, None
        elif _is_ancestor(git, left, right):
            src_side, dst_side, src_oid, dst_oid = "gitlab", "hub", right, left
        elif _is_ancestor(git, right, left):
            src_side, dst_side, src_oid, dst_oid = "hub", "gitlab", left, right
        else:
            holds.append({"ref": ref, "reason": "diverged"})
            continue
        if dst_oid is None:
            dst_seen = state["seen"][dst_side].get(ref)
            if dst_seen:
                holds.append({"ref": ref, "reason": "destination-ref-missing-but-seen", "side": dst_side})
                continue
        if dst_side == "hub" and ref.startswith("refs/heads/"):
            checked = _checked_out_branches(git, Path(cfg["hub"]))
            branch = ref.removeprefix("refs/heads/")
            if branch in checked:
                holds.append({"ref": ref, "reason": "hub-branch-checked-out"})
                continue
        remote = "hub" if dst_side == "hub" else "gitlab"
        creating = dst_oid is None
        if creating:
            _record_pending_create(state, dst_side, ref, src_oid)
            _atomic_json(state_path, state)
        try:
            _push(git, dst_side, remote, src_side, ref, src_oid)
        except WorkerError as exc:
            message = str(exc)
            if "deadline" in message or "timed out" in message:
                raise
            holds.append({"ref": ref, "reason": "push-failed", "side": dst_side})
            actions.append({"ref": ref, "direction": f"{src_side}-to-{dst_side}", "result": "push-failed"})
            continue
        # Freshly read the destination before proceeding. A post-push race is held.
        verified = _parse_ls_remote(git.run("ls-remote", "--refs", remote)).get(ref)
        if verified != src_oid:
            if verified:
                _archive_observed_remote_tip(git, remote, dst_side, ref, verified, run_id)
            if verified and _is_ancestor(git, src_oid, verified):
                _update_source_tracking(git, dst_side, ref, verified)
                if creating:
                    _confirm_created_ref(state, dst_side, ref, verified)
                    _atomic_json(state_path, state)
                actions.append({"ref": ref, "direction": f"{src_side}-to-{dst_side}", "result": "advanced-concurrently"})
            else:
                if creating and verified is not None:
                    _mark_ref_conflict(state, dst_side, ref, verified)
                    _atomic_json(state_path, state)
                holds.append({"ref": ref, "reason": "destination-changed-after-push"})
                continue
        else:
            if creating:
                _confirm_created_ref(state, dst_side, ref, src_oid)
                _atomic_json(state_path, state)
            actions.append({"ref": ref, "direction": f"{src_side}-to-{dst_side}", "result": "fast-forwarded"})
    return actions, holds


def _new_state() -> dict:
    return {"schema": SCHEMA, "seen": {"hub": {}, "gitlab": {}}, "last_run": None}


def _safe_existing_state_dir(cfg: dict) -> Path | None:
    """Return an existing internal state directory safe for failure receipts."""
    state_dir = Path(cfg["state_dir"])
    if state_dir.is_symlink() or not state_dir.is_dir():
        return None
    resolved = state_dir.resolve()
    roots = [Path("/Volumes").resolve()]
    roots.extend(Path(v["path"]).resolve() for v in cfg.get("volumes", []))
    for root in roots:
        try:
            resolved.relative_to(root)
            return None
        except ValueError:
            continue
    return state_dir


def _cleanup_fetch_refs(git: Git, run_id: str) -> None:
    prefix = f"{FETCH_NS}/{run_id}/"
    refs = git.run("for-each-ref", "--format=%(refname)", prefix, check=False).splitlines()
    if refs:
        commands = ["start", *(f"delete {ref}" for ref in refs), "prepare", "commit"]
        git.run("update-ref", "--stdin", input_data="\n".join(commands) + "\n")


def _ensure_cache(cfg: dict, executable: str, initialize: bool, deadline: float) -> tuple[Path, Path]:
    cache = Path(cfg["cache"])
    state_dir = Path(cfg["state_dir"])
    marker = cache / MARKER_NAME
    state_path = state_dir / "refs.json"
    existed_before = cache.exists()
    if not cache.exists():
        if not initialize:
            raise WorkerError("cache is missing; run --initialize explicitly", code=2)
        cache.mkdir(parents=True, exist_ok=True)
    identity = _identity(cfg)
    if initialize:
        if marker.exists():
            marker_value = _read_json(marker)
            if marker_value.get("identity") != identity or marker_value.get("phase") != "initializing":
                raise WorkerError("cache is already initialized or belongs to another config", code=2)
        else:
            if existed_before and any(cache.iterdir()):
                raise WorkerError("refusing to adopt an existing unowned cache", code=2)
            _atomic_json(marker, {"identity": identity, "phase": "initializing", "started_at": _now()})
    elif not marker.exists():
        raise WorkerError("cache has no worker identity marker", code=2)
    if not (cache / "HEAD").exists():
        if not initialize:
            raise WorkerError("cache is not initialized", code=2)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerError("run deadline exceeded during cache initialization")
        result = subprocess.run([executable, "init", "--bare", str(cache)], env=_clean_git_env(),
                                capture_output=True, timeout=min(10.0, remaining), check=False)
        if result.returncode:
            raise WorkerError("could not initialize dedicated bare cache", code=2)
    if _git_direct(executable, "--git-dir", str(cache), "rev-parse", "--is-bare-repository",
                   deadline=deadline) != "true":
        raise WorkerError("cache must be a bare Git repository", code=2)
    worktrees = _git_direct(executable, "--git-dir", str(cache), "worktree", "list", "--porcelain",
                            deadline=deadline)
    if len([x for x in worktrees.splitlines() if x.startswith("worktree ")]) != 1:
        raise WorkerError("cache must be dedicated and have no worktrees", code=2)
    if initialize:
        remotes = _git_direct(executable, "--git-dir", str(cache), "remote", deadline=deadline).splitlines()
        expected = {"hub": str(Path(cfg["hub"]).resolve()), "gitlab": cfg["gitlab"]}
        for name, url in expected.items():
            if name not in remotes:
                _git_direct(executable, "--git-dir", str(cache), "remote", "add", name, url, deadline=deadline)
        current = _git_direct(executable, "--git-dir", str(cache), "remote", deadline=deadline).splitlines()
        if set(current) - set(expected):
            raise WorkerError("cache has unexpected remotes", code=2)
    else:
        marker_value = _read_json(marker)
        if marker_value.get("identity") != identity or marker_value.get("phase") != "initialized":
            raise WorkerError("cache identity does not match config", code=2)
        remotes = _git_direct(executable, "--git-dir", str(cache), "remote", deadline=deadline).splitlines()
        if set(remotes) != {"hub", "gitlab"}:
            raise WorkerError("cache remotes do not match expected identity", code=2)
    expected_urls = {"hub": str(Path(cfg["hub"]).resolve()), "gitlab": cfg["gitlab"]}
    for name, url in expected_urls.items():
        fetch_urls = _git_direct(executable, "--git-dir", str(cache), "remote", "get-url", "--all", name,
                                 deadline=deadline).splitlines()
        push_urls = _git_direct(executable, "--git-dir", str(cache), "remote", "get-url", "--push", "--all", name,
                                deadline=deadline).splitlines()
        if fetch_urls != [url] or push_urls != [url]:
            raise WorkerError("cache fetch/push remote URL mismatch", code=2)
    return cache, state_path


def _run(cfg: dict, initialize: bool = False, *, deadline: float) -> tuple[int, dict]:
    executable = cfg["git"]
    state_dir = Path(cfg["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "run.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 3, {"status": "lock-busy", "at": _now()}
        cache, state_path = _ensure_cache(cfg, executable, initialize, deadline)
        git = Git(executable, cache, deadline, cfg["command_timeout_s"])
        run_id = uuid.uuid4().hex
        started = _now()
        if initialize:
            if state_path.exists():
                prior = _read_json(state_path)
                last = prior.get("last_run") or {}
                if prior.get("schema") == SCHEMA and last.get("mode") == "initialize":
                    marker = _read_json(cache / MARKER_NAME)
                    if marker.get("identity") != _identity(cfg) or marker.get("phase") != "initializing":
                        raise WorkerError("initialization state/marker mismatch", code=2)
                    marker["phase"] = "initialized"
                    marker["initialized_at"] = _now()
                    _atomic_json(cache / MARKER_NAME, marker)
                    result = {"status": "initialized", "run_id": last.get("id"),
                              "observed": {s: len(prior["seen"][s]) for s in ("hub", "gitlab")},
                              "actions": [], "pending": last.get("pending", [])}
                    _atomic_json(state_dir / "status.json", result)
                    return 0, result
                raise WorkerError("baseline state exists but is not a completed initialization", code=2)
            state = _new_state()
        else:
            state = _read_json(state_path)
            if state.get("schema") != SCHEMA or not isinstance(state.get("seen"), dict):
                raise WorkerError("mirror state schema is invalid", code=2)
            for side in ("hub", "gitlab"):
                if not isinstance(state["seen"].get(side), dict):
                    raise WorkerError("mirror state is incomplete", code=2)
        try:
            snapshots = {
                "hub": _snapshot(git, "hub", "hub", run_id),
                "gitlab": _snapshot(git, "gitlab", "gitlab", run_id),
            }
            _update_source_refs(git, state, snapshots, run_id)
        except WorkerError:
            _cleanup_fetch_refs(git, run_id)
            raise
        deletion_holds = _advance_seen(state, snapshots)
        if initialize:
            # Baseline only: record exactly what exists and do not send pushes.
            state["last_run"] = {"id": run_id, "at": started, "mode": "initialize", "actions": [],
                                 "pending": deletion_holds, "errors": []}
            _atomic_json(state_path, state)
            _atomic_json(cache / MARKER_NAME, {"identity": _identity(cfg), "phase": "initialized",
                                                "started_at": started, "initialized_at": started})
            result = {"status": "initialized", "run_id": run_id, "observed": {
                side: len(snapshots[side]) for side in ("hub", "gitlab")}, "actions": [], "pending": deletion_holds}
            _atomic_json(state_dir / "status.json", result)
            return 0, result
        # Persist first-seen refs and deletions before any outbound push. A
        # failed push or final poll must not erase a deletion observation.
        state["last_run"] = {"id": run_id, "at": started, "mode": "sync", "actions": [],
                             "pending": deletion_holds, "errors": []}
        _atomic_json(state_path, state)
        try:
            actions, holds = _sync_refs(git, cfg, state, state_path, snapshots, deletion_holds, run_id)
        finally:
            _cleanup_fetch_refs(git, run_id)
        # Refresh once after all pushes; failed snapshots never authorize a push.
        final = {
            "hub": _parse_ls_remote(git.run("ls-remote", "--refs", "hub")),
            "gitlab": _parse_ls_remote(git.run("ls-remote", "--refs", "gitlab")),
        }
        holds.extend(_advance_seen(state, final, update_oids=False))
        state["last_run"] = {"id": run_id, "at": started, "mode": "sync", "actions": actions,
                             "pending": holds, "errors": []}
        _atomic_json(state_path, state)
        result = {"status": "ok" if not holds else "held", "run_id": run_id,
                  "actions": actions, "pending": holds, "observed": {
                      side: len(final[side]) for side in ("hub", "gitlab")}}
        _atomic_json(state_dir / "status.json", result)
        return (1 if any(item.get("reason") == "push-failed" for item in holds) else 0), result
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--initialize", action="store_true", help="capture baseline without pushing")
    args = parser.parse_args(argv)
    cfg = None
    deadline = None
    try:
        cfg = _load_config(args.config)
        deadline = time.monotonic() + cfg["run_timeout_s"]
        _validate_volumes(cfg, deadline)
        _validate_local_repositories(cfg, cfg["git"], deadline)
        code, result = _run(cfg, args.initialize, deadline=deadline)
    except WorkerError as exc:
        result = {"status": "error", "error": str(exc), "at": _now()}
        if cfg is not None:
            safe_dir = _safe_existing_state_dir(cfg)
            if safe_dir is not None:
                _atomic_json(safe_dir / "status.json", result, create_parent=False)
        code = exc.code
    except Exception as exc:
        # Fail closed while avoiding exception text that may carry remote/config details.
        result = {"status": "error", "error": f"unexpected {type(exc).__name__}", "at": _now()}
        if cfg is not None:
            safe_dir = _safe_existing_state_dir(cfg)
            if safe_dir is not None:
                _atomic_json(safe_dir / "status.json", result, create_parent=False)
        code = 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
