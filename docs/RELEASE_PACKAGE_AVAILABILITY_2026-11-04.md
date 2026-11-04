# fDisBull offline package availability and verification: 2026-11-04

**Scope:** release/source metadata inspection and download attempt. **No package bytes have been downloaded, unpacked or executed in this environment.** The connected GitLab project is readable; network access to GitLab's generic package file endpoint failed here. Never report download success from a link or package-registry listing alone.

| Requirement | Current evidence | Status |
|---|---|---|
| Latest published version | GitLab [v0.31.1](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.31.1), tag `e94bae0fca9d6ffc090991e8daad04772a5ff32c` | Published, 2026-11-03 |
| v0.31.1 **tool** bundle | Generic package `fdisbull-tool-packages`, version `0.31.1-20261103`; core/player wheels, sdist and tool ZIP | Release metadata and repo hashes verified; local bytes unavailable |
| Latest explicitly advertised **complete Linux offline** kit | [v0.29.0 release packages](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804), version `0.29.0-20261101`; native kit, third-party dependency kit, source companion, checksums | Historical 0.29.0 kit only; **not** a 0.31.1 offline kit |
| Next version | [v0.32 draft !78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78) with exact-source Linux gates in progress | Not tagged, published or installed |

## Latest published tool-package hashes

Pinned against [v0.31.1 release evidence](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/v0.31.1/docs/evidence/0.31.1-release/README.md):

| Artifact | Expected size (bytes) | SHA-256 |
|---|---:|---|
| `fdisbull-0.31.1-tool.zip` | 6,390,059 | `81db8e19349b6fb26ea2f91b7de79ed8ba1f3691c3d7f9eaec7ed04c7f5eb5c3` |
| `fdisbull-0.31.1-py3-none-any.whl` | 1,895,364 | `03bf5142aab0a9448c73b38c986ddeef92f68eab2630f6f1ef4842bb2364bf33` |
| `fdisbull_player-0.31.1-py3-none-any.whl` | 86,674 | `6b5098b8ad425579bb50bfd5d12fb4a6cfd362b45a863b3fd4937cbeedfa20a3` |
| `fdisbull-0.31.1.tar.gz` | 5,260,503 | `bd37507e6d91f0e3279f780b5238279a2b86fd02adc649ea1fe394cdde26b72c` |

The known GitLab API generic-package route has the form `https://gitlab.com/api/v4/projects/88349936/packages/generic/fdisbull-tool-packages/0.31.1-20261103/<filename>`. **This is a path construction from published package naming and GitLab's documented registry shape, not an independently fetched asset URL in this session.** Require HTTP success, exact size/hash and archive privacy inspection before using it. A release Git source ZIP is **not** a Linux no-index/offline installation.

## Last independently documented full offline kit

The [0.29.0 release](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.29.0) and its [release package page](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804) document:

- Full Linux native offline-kit SHA-256: `b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f`.
- Linux x86-64 / Python 3.13 third-party dependency bundle SHA-256: `e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.
- Historical fresh no-index install plus native acceptance passed for **that 0.29.0 source cut only**. It does not establish that the same kit is compatible with 0.31.1.

## Required next release/download gate

1. Fetch v0.31.1 tool ZIP/core/player/sdist through a network-enabled client and rehash against the exact values above. Record HTTP URL, time, bytes, hash, source commit, environment and destination.
2. For **full offline Linux operation**, build/publish an exact-source 0.31.1 native offline kit with the supported build scripts, the pinned DOSBox runtime, source companion, Python interpreter ABI and all pinned dependency wheels. Validate extracted files and archive contents against source and privacy selectors.
3. Fresh, isolated `--no-index` install, run the original/UIL/UDC smoke gates, native backend doctors and exact-source acceptance. Reusing an older kit requires an explicit dependency/ABI compatibility proof, **not** copying its success report.
4. Publish/download/hash-check release assets only after all required gates; never promote draft !78 merely because a limited local suite passed.
5. Provide a verified artifact path/link and a checked `delivery_receipt`. Until then, mark the request **partial: package located, download blocked**.
