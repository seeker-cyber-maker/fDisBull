"""Verify two-way mirror reconciliation and GitLab CI pipeline-suppression rules."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync_mirrors.py"
SPEC = importlib.util.spec_from_file_location("sync_mirrors", SCRIPT)
mirror = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mirror)


def test_build_push_commands_suppresses_gitlab_ci_on_topic_branches():
    cmds = mirror.build_push_commands(
        remote="gitlab",
        is_gitlab=True,
        branches=["main", "codex/common-uil-contract-20261101", "fix/review-dos-data-receipts"],
        include_tags=True,
        ci_on_main=False,
    )
    assert all(cmd[:4] == ["git", "push", "-o", "ci.skip"] for cmd in cmds)

    cmds_ci_main = mirror.build_push_commands(
        remote="gitlab",
        is_gitlab=True,
        branches=["main", "codex/common-uil-contract-20261101"],
        include_tags=False,
        ci_on_main=True,
    )
    assert cmds_ci_main[0] == ["git", "push", "gitlab", "refs/heads/main:refs/heads/main"]
    assert cmds_ci_main[1] == [
        "git",
        "push",
        "-o",
        "ci.skip",
        "gitlab",
        "refs/heads/codex/common-uil-contract-20261101:refs/heads/codex/common-uil-contract-20261101",
    ]


def test_reconcile_with_remote_fast_forwards_behind_local_branch_and_skips_synced(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    (repo / "README.md").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "v1"], check=True)
    sha1 = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    (repo / "README.md").write_text("v2\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-am", "v2"], check=True)
    sha2 = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    # Set local branch behind remote tracking ref (simulating pr-local/56-miniplanets-display-20261031)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/topic-behind", sha1], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/gitlab/topic-behind", sha2], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/gitlab/main", sha2], check=True)

    plan = mirror.reconcile_with_remote(repo, "gitlab", dry_run=False)
    assert "main" in plan["already_synced"]
    assert "topic-behind" in plan["fast_forwarded_local"]
    assert plan["to_push"] == []
    updated_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "refs/heads/topic-behind"], text=True
    ).strip()
    assert updated_sha == sha2


def test_sync_mirrors_refuses_retired_github_remote(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    (repo / "README.md").write_text("ok\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/seeker-cyber-maker/fDisBull.git"],
        check=True,
    )
    with pytest.raises(mirror.MirrorSyncError, match="Refusing to push to retired GitHub remote"):
        mirror.sync_mirrors(repo, remotes=("origin",), dry_run=True)


def test_gitlab_ci_yaml_enforces_trial_safe_workflow_rules():
    ci_path = ROOT / ".gitlab-ci.yml"
    if not ci_path.is_file():
        pytest.skip("Repository checkout only")
    ci_text = ci_path.read_text()
    assert "workflow:" in ci_text
    assert '$CI_COMMIT_MESSAGE =~ /\\[(skip ci|ci skip)\\]/i' in ci_text
    assert '$CI_PIPELINE_SOURCE == "merge_request_event"' in ci_text
    assert '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH' in ci_text
    assert "interruptible: true" in ci_text
    assert "retry: 0" in ci_text
    assert 'resource_group: "fdisbull-verify-$CI_COMMIT_REF_SLUG"' in ci_text
    assert "when: manual" in ci_text
