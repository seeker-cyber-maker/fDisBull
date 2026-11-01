# ChatGPT fDisBull/Zork/KQ1 agent handoff — 2026-11-01

> **Documentation-only, evidence-scoped snapshot.** Do not confuse a GitLab draft MR with integrated `main`, or a Library-held movie with a GitLab release asset. No original game binaries, saves, raw captures, or private token material are included. This is a handoff, not merge authorization.

## GitLab source of truth

- Private project: [brewster-jennings-group/fdisbull](https://gitlab.com/brewster-jennings-group/fdisbull), ID `88349936`.
- Audited `main` before this documentation commit: `498c0887f8d15ca3b2fb3dc8994d2de24e144273`. This note does **not** claim new runtime integration.
- [Release v0.29.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.29.0) is immutable tag `09a820952ad3f54d0d0707db0515a8010f7eceb1`, built from source `c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`.
- MR [!26](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/26) merged at `a6ac7ac7f60fc97bc1bf69db7368ff07ff27301e`, **after** release tag publication. It did not change the tag.
- The release contains 10 package files: 6 in [native/dependency packages](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804), 4 in [tool packages](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791785). This agent could independently hash-check Library copies of the dependency archive and sdist; the native 103 MB offline kit and 107 MB source companion were not obtained in this session.
- Agent download support is committed on `main` under [release-assets/v0.29.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/main/release-assets/v0.29.0): verified [download script](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/main/release-assets/v0.29.0/fdisbull-0.29.0-fetch-verify.py) and [checksum inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/main/release-assets/v0.29.0/fdisbull-v0.29.0-release-inventory.json). The two file bytes were read back and their hashes matched, at `498c0887`.
- GitLab showed no project CI pipelines in this agent's list query. Historical **local** Linux/container tests in the v0.29 release notes are not hosted CI acceptance.

## Zork conversion and game-intent UIL

- `main` retains the lower-level Z-machine processor, original word16 executable IR, and earlier intent runtime.
- The **complete recovered scene/window semantic consumer is not on main**. It is preserved under draft MR [!36](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/36), source branch `pr/32/zork-scene-uil-20261030` at `4be05579bc623aa65bfe554a9ecd62dc4b90bd0e`. The reviewed MR explicitly reports source divergence (96 behind/5 ahead), 49 changed paths/31 paths absent on main, plus three named conflicts. Review and rebase are required; **do not silently merge**.
- Preserved source handles 110 room definitions and 352 directional exits (277 direct, 37 blocked, 25 conditional, six door, seven residual). Window OPEN/CLOSE named semantic operations remain qualified to their live guards, text/turn/RNG effects and residual source boundaries; historic evidence is in the MR, not a new test run in this audit.
- The investigation methodology starts from required semantic scene elements, consults direct object/property/table records, narrows unresolved dependency slices, keeps typed constants and live predicates separate, preserves unknown effects as IR, and checks full state/output/turn/suspend parity.
- Next task: reconcile `!36` against current main without losing newer media/native/CLI/distribution paths; run genuine fresh tests from the merged tree before changing draft status.

## King's Quest I TAS handoff

- A separate **JPC-RR 11.2** power-on fixed-input movie recreation completed two variants, each replayed twice with byte-identical native captures. This material is retained in the coordinator's ChatGPT Library rather than GitLab.
- 63-point automatic ending: **29.891690004 seconds** from final intro Escape press to the displayed king-steps-aside message; 66-point ordinary `BOW` variant: **29.506450680 seconds** (0.385239324 seconds faster). Both reach the credits. Host processing/capture wall times were **66.5–67.9 seconds** for each roughly 35-second native capture.
- Neither movie reproduces Robb's 9.89-second clip, represents an optimized record, or has TASVideos publication acceptance. Keep native emulator time and host processing time distinct.
- Historical TAS/code and cave experiments have separate draft review chains, including [!17](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/17), [!21](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/21), [!33](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/33), and frame/input draft [!30](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/30). These do not establish the independent JPC-RR movie as published GitLab code. Do not add game bytes or unqualified emulator assets to Git.

## Next-owner checklist

1. Read current `main`, release tag, package manifests, and relevant draft MR heads **afresh**; label each claim verified/reported/unverified.
2. For Zork, reconcile and test draft !36. Keep the low-level IR and existing tests intact; do not substitute decoded routine names for recovered game intent.
3. For the 0.29 package, let an authorized agent run the exact [download-and-verify helper](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/main/release-assets/v0.29.0/fdisbull-0.29.0-fetch-verify.py) and commit a ten-file SHA-256 receipt. Do not treat this documentation commit as a binary upload.
4. For KQ1, obtain the coordinator-held JPC-RR movie bundle and use recorded fixed-input replay before claiming a different time. Preserve original hashes; no native game edits or binaries in Git.
5. After each material new commit/experiment, publish a **delta handoff** with base SHA, head SHA, files changed, source/evidence, fresh tests, unsatisfied constraints and the next safe action. No background work is implied.

**Audit type:** One agent's synchronous snapshot, not a repository-wide acceptance or a claim that other agents have completed their drafts.
