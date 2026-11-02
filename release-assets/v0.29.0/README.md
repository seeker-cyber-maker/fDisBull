# fDisBull v0.29.0 — agent download helpers

These are **post-release support files** for the published [v0.29.0 GitLab release](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.29.0). They do not alter the immutable release tag, the original ten package binaries, or their checksums.

- [Download and SHA-256 verify all ten package files](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/main/release-assets/v0.29.0/fdisbull-0.29.0-fetch-verify.py)
- [Machine-readable release inventory and publisher hashes](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/main/release-assets/v0.29.0/fdisbull-v0.29.0-release-inventory.json)

The Python helper requires Python 3.10+, plus a GitLab token authorized to read project `88349936`. Use an existing authenticated `glab auth login` session, or supply `GITLAB_TOKEN` in the agent's own environment. Never put tokens in a prompt, repository file, logs, or release metadata.

```bash
python3 fdisbull-0.29.0-fetch-verify.py --output ./fdisbull-v0.29.0-full
```

The helper checks the release tag's commit ID, both package groups, the ten distinct filenames, their GitLab file hashes and known publisher hashes, their sizes where supplied, and the downloaded `SHA256SUMS`. It writes `VERIFIED-DOWNLOAD.json` only after verification.

Package groups (existing binaries; *not* duplicated here):
- [Native Linux and dependency files](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804)
- [Wheels, sdist and tool ZIP](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791785)

These two helper files are **not** native package artifacts, and the package registry still has the original 10 files. This support directory is on the GitLab repository's `main` branch because the v0.29.0 tag is intentionally frozen.
