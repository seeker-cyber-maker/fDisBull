"""Skip a feature-branch push only when an open PR will run its checks.

API errors fail open: duplicate work is preferable to losing the first check.
No write permissions or pull_request_target execution required.
"""
import json
import os
import urllib.parse
import urllib.request


def protected(ref):
    return (ref == "refs/heads/main" or ref.startswith(("refs/heads/integration/", "refs/heads/release/"))
            or ref.startswith("refs/heads/") and ref.endswith("-integration"))


def should_run(event, ref, repository, pulls, sha):
    if event != "push" or not ref.startswith("refs/heads/") or protected(ref):
        return True
    branch = ref.removeprefix("refs/heads/")
    return not any(p["state"] == "open" and p.get("mergeable") is True
                   and p["head"]["sha"] == sha and p["head"]["ref"] == branch
                   and p["head"]["repo"] is not None
                   and p["head"]["repo"]["full_name"] == repository for p in pulls)


def main():
    event, ref, repo = (os.environ[k] for k in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_REPOSITORY"))
    run = True
    if event == "push" and ref.startswith("refs/heads/") and not protected(ref):
        query = urllib.parse.urlencode({"state": "open", "head": repo.split("/")[0] + ":" + ref.removeprefix("refs/heads/"), "per_page": 100})
        request = urllib.request.Request(f"https://api.github.com/repos/{repo}/pulls?{query}", headers={
            "Accept": "application/vnd.github+json", "User-Agent": "fdisbull-ci-event-policy"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                pulls = json.load(response)
            # Conflicting PRs cannot run pull_request workflows. Unknown mergeability
            # also keeps the push checks; never assume that an open PR suffices.
            details = []
            for pull in pulls:
                if pull["head"]["repo"] and pull["head"]["repo"]["full_name"] == repo:
                    detail = urllib.request.Request(
                        f"https://api.github.com/repos/{repo}/pulls/{int(pull['number'])}",
                        headers={"Accept": "application/vnd.github+json", "User-Agent": "fdisbull-ci-event-policy"})
                    with urllib.request.urlopen(detail, timeout=20) as response:
                        details.append(json.load(response))
            run = should_run(event, ref, repo, details, os.environ["GITHUB_SHA"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"PR lookup unavailable; keeping branch checks: {type(exc).__name__}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"run={str(run).lower()}\n")


if __name__ == "__main__":
    main()
