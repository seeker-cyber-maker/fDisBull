"""Local-only contract tests for the optional GitHub mirror peer."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

from test_mirror_sync_service import cmd, git, mirrors


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "scripts" / "mirror_sync_service.py"
_spec = importlib.util.spec_from_file_location("mirror_sync_service", SERVICE_PATH)
service = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = service
_spec.loader.exec_module(service)

GITHUB_URL = "https://github.com/seeker-cyber-maker/fDisBull.git"


def github_config(m, **overrides):
    cfg = json.loads(m["config"].read_text())
    cfg["github"] = {
        "url": GITHUB_URL,
        "cache": str(m["root"] / "github-cache.git"),
        "state_dir": str(m["root"] / "github-state"),
        "tag_exceptions": [],
    }
    cfg.update(overrides)
    return cfg


def test_github_peer_is_opt_in_and_rejects_other_github_urls(mirrors, tmp_path):
    m = mirrors
    legacy = service._load_config(m["config"])
    assert "github" not in legacy

    cfg = github_config(m)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    loaded = service._load_config(path)
    peer = service._github_config(loaded)
    assert peer["gitlab"] == GITHUB_URL
    assert peer["cache"] == cfg["github"]["cache"]
    assert peer["state_dir"] == cfg["github"]["state_dir"]
    assert peer["_peer_kind"] == "github"
    assert peer["_tag_exceptions"] == []

    for url in (
        "https://github.com/another/project.git",
        "https://github.com/seeker-cyber-maker/other.git",
        "https://api.github.com/seeker-cyber-maker/fDisBull.git",
        "https://evil.example/github.com/seeker-cyber-maker/fDisBull.git",
    ):
        invalid = github_config(m)
        invalid["github"]["url"] = url
        path.write_text(json.dumps(invalid))
        with pytest.raises(service.WorkerError):
            service._load_config(path)


def test_tag_exception_requires_exact_pair_and_matching_peeled_commit(mirrors):
    m = mirrors
    tag_ref = "refs/tags/restored"
    # Two distinct annotated tag objects point at the same commit.
    git(m, "-C", m["seed"], "tag", "-a", "left", m["base"], "-m", "left")
    git(m, "-C", m["seed"], "tag", "-a", "right", m["base"], "-m", "right")
    left = git(m, "-C", m["seed"], "rev-parse", "refs/tags/left").stdout.strip()
    right = git(m, "-C", m["seed"], "rev-parse", "refs/tags/right").stdout.strip()
    cfg = github_config(m)
    cfg["_peer_kind"] = "github"
    cfg["_tag_exceptions"] = [dict(ref=tag_ref, hub_oid=left, peer_oid=right,
                                    peeled_commit=m["base"])]
    fake_git = service.Git(executable="git", cache=m["seed"], deadline=time.monotonic() + 5,
                           command_timeout=5)

    assert service._accepted_tag_exception(fake_git, cfg, tag_ref, left, right)
    assert not service._accepted_tag_exception(fake_git, cfg, "refs/tags/other", left, right)
    assert not service._accepted_tag_exception(fake_git, cfg, tag_ref, right, left)
    cfg["_tag_exceptions"][0]["peeled_commit"] = "0" * 40
    assert not service._accepted_tag_exception(fake_git, cfg, tag_ref, left, right)
    cfg["_peer_kind"] = "gitlab"
    cfg["_tag_exceptions"][0]["peeled_commit"] = m["base"]
    assert not service._accepted_tag_exception(fake_git, cfg, tag_ref, left, right)


def test_topology_push_options_are_provider_specific(mirrors):
    m = mirrors
    github = m["root"] / "github.git"
    cmd("git", "init", "--bare", github, env=m["env"])
    cmd("git", "--git-dir", github, "config", "receive.advertisePushOptions", "true", env=m["env"])
    hook = github / "hooks" / "pre-receive"
    hook.write_text('#!/bin/sh\n[ "${GIT_PUSH_OPTION_COUNT:-0}" = 0 ] || exit 1\ncat >/dev/null\n')
    hook.chmod(0o755)
    raw = github_config(m)
    raw["github"]["cache"] = str(m["root"] / "github-cache.git")
    raw["github"]["state_dir"] = str(m["root"] / "github-state")
    path = m["root"] / "topology-config.json"
    path.write_text(json.dumps(raw))
    cfg = service._load_config(path)
    # Swap only transport endpoints after validating the exact production URL.
    cfg["github"]["url"] = str(github)

    code, result = service._run_topology(cfg, initialize=True,
                                          deadline=time.monotonic() + 20)
    assert code == 0, result
    commit = git(m, "commit-tree", git(m, "rev-parse", "HEAD^{tree}").stdout.strip(),
                 "-p", m["base"], "-m", "publish through topology").stdout.strip()
    git(m, "update-ref", "refs/heads/new", commit)
    cmd("git", "-C", m["seed"], "push", m["hub"],
        f"{commit}:refs/heads/new", env=m["env"])
    code, result = service._run_topology(cfg,
                                          deadline=time.monotonic() + 20)
    assert code == 0, result
    assert cmd("git", "--git-dir", m["remote"], "rev-parse", "refs/heads/new", env=m["env"]).stdout.strip() == commit
    assert cmd("git", "--git-dir", github, "rev-parse", "refs/heads/new", env=m["env"]).stdout.strip() == commit
    assert (m["remote"] / "push-options.log").read_text().splitlines()[-1] == "ci.skip"

    # A GitHub-origin update reaches the hub and GitLab. The GitHub receiver
    # hook above rejects any push option, so successful convergence proves the
    # coordinator omits ci.skip for that provider.
    github_commit = git(m, "commit-tree", git(m, "rev-parse", "HEAD^{tree}").stdout.strip(),
                        "-p", m["base"], "-m", "incoming from GitHub").stdout.strip()
    cmd("git", "-C", m["seed"], "push", github,
        f"{github_commit}:refs/heads/main", env=m["env"])
    code, result = service._run_topology(cfg, deadline=time.monotonic() + 20)
    assert code == 0, result
    assert cmd("git", "--git-dir", m["hub"], "rev-parse", "refs/heads/main", env=m["env"]).stdout.strip() == github_commit
    assert cmd("git", "--git-dir", m["remote"], "rev-parse", "refs/heads/main", env=m["env"]).stdout.strip() == github_commit

    # A later GitLab-origin descendant is copied to the hub first and reaches
    # GitHub in the coordinator's bounded followup pass.
    gitlab_commit = git(m, "commit-tree", git(m, "rev-parse", "HEAD^{tree}").stdout.strip(),
                        "-p", github_commit, "-m", "incoming from GitLab").stdout.strip()
    cmd("git", "-C", m["seed"], "push", "-o", "ci.skip", m["remote"],
        f"{gitlab_commit}:refs/heads/main", env=m["env"])
    code, result = service._run_topology(cfg, deadline=time.monotonic() + 20)
    assert code == 0, result
    assert "github_followup" in result["peers"]
    assert cmd("git", "--git-dir", m["hub"], "rev-parse", "refs/heads/main", env=m["env"]).stdout.strip() == gitlab_commit
    assert cmd("git", "--git-dir", github, "rev-parse", "refs/heads/main", env=m["env"]).stdout.strip() == gitlab_commit


def test_topology_lock_serializes_concurrent_invocation(mirrors):
    m = mirrors
    cfg = service._load_config(m["config"])
    state = Path(cfg["state_dir"])
    state.mkdir(parents=True)
    lock_fd = __import__("os").open(state / "topology.lock", __import__("os").O_CREAT | __import__("os").O_RDWR, 0o600)
    import fcntl
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        code, result = service._run_topology(cfg, deadline=time.monotonic() + 5)
        assert code == 3
        assert result["status"] == "lock-busy"
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        __import__("os").close(lock_fd)
