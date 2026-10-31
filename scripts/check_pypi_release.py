#!/usr/bin/env python3
"""Fail closed before building an explicitly selected, previously tested release."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def check_source(root: Path, tag: str, sha: str) -> str:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Use a stable vMAJOR.MINOR.PATCH tag")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Use the full lowercase source commit SHA")
    if git(root, "rev-parse", "HEAD") != sha:
        raise ValueError("Checked-out source does not match the requested SHA")
    if git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}") != sha:
        raise ValueError("Tag does not match the requested SHA")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "origin/main"], check=True)
    version = tag[1:]
    for manifest in ("pyproject.toml", "player/pyproject.toml"):
        if tomllib.loads((root / manifest).read_text())["project"]["version"] != version:
            raise ValueError(f"Tag/version mismatch: {manifest}")
    module = ast.parse((root / "src/fdisbull/__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if versions != [version]:
        raise ValueError("Tag/version mismatch: fdisbull.__version__")
    if git(root, "status", "--porcelain"):
        raise ValueError("Release source must be a clean checkout")
    return version


def check_license(root: Path, enabled: str, ready: str) -> None:
    if enabled != "true" or ready != "true":
        raise ValueError("Publication disabled: PYPI_PUBLISH_ENABLED and PYPI_LICENSE_READY must both be true")
    # Readiness is a maintainer decision. Also reject accidentally empty metadata.
    for manifest in ("pyproject.toml", "player/pyproject.toml"):
        if not tomllib.loads((root / manifest).read_text())["project"].get("license"):
            raise ValueError(f"License metadata is still missing: {manifest}")


def successful_run(runs: list[dict], sha: str, workflow: str) -> dict:
    eligible = [run for run in runs if run["head_sha"] == sha
                and run["event"] in {"push", "workflow_dispatch"}
                and run["path"] == f".github/workflows/{workflow}"
                and run["head_repository"]["full_name"] == "seeker-cyber-maker/fDisBull"]
    latest = max(eligible, key=lambda run: run["id"], default=None)
    if latest is None or latest["status"] != "completed" or latest["conclusion"] != "success":
        raise ValueError(f"Latest trusted {workflow} run must succeed on exact SHA {sha}")
    return latest


def check_ci(sha: str) -> None:
    for workflow in ("ci.yml", "native-debugger.yml"):
        query = urlencode({"head_sha": sha, "per_page": 100})
        url = f"https://api.github.com/repos/seeker-cyber-maker/fDisBull/actions/workflows/{workflow}/runs?{query}"
        request = Request(url, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                        "Accept": "application/vnd.github+json"})
        with urlopen(request, timeout=30) as response:
            runs = json.load(response)["workflow_runs"]
        # A bounded result fails closed if the required run is no longer present.
        print(successful_run(runs, sha, workflow)["html_url"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--target", choices=("validate", "testpypi", "pypi"), default="validate")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if os.environ.get("GITHUB_REPOSITORY") != "seeker-cyber-maker/fDisBull" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        parser.error("Dispatch this workflow from seeker-cyber-maker/fDisBull main only")
    version = check_source(root, args.tag, args.sha)
    if args.target != "validate":
        check_license(root, os.environ.get("PYPI_PUBLISH_ENABLED", ""), os.environ.get("PYPI_LICENSE_READY", ""))
    check_ci(args.sha)
    print(f"Verified release source: {args.sha}, version {version}, target {args.target}")


if __name__ == "__main__":
    main()
