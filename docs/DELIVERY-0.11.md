# Published 0.11.0 delivery — 2026-10-23

The [GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.11.0) targets source commit `a2167479a6ee474e8a4e2a7965c8ef46c618df54`. Its wheel, source distribution and tool ZIP are the unmodified outputs of [tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891689). `SHA256SUMS` and `VERIFICATION-0.11.0.json` are also attached.

The user-designated DeepSeek delivery is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.11.0-a216747/
```

Start with `README-DEEPSEEK.md` there. The folder contains the exact published assets, the tested Mac ARM64 layers backend, its complete source patch, pinned source manifest, upstream GPL notices, library dependency list, focused verification receipts and source-only navigation route. `fdisbull_from_delivery.py` runs the exact wheel with an existing Python 3.12+ dependency environment. No existing agent environment was replaced.

The sibling bundle is `fdisbull-native-debugger-0.11.0-published-2026-10-23-a216747.zip`, SHA-256:

```text
858d6106213b283ddf7e98fb93ba8bfb5aec75bca4164908b6c68c313e9db24a
```

The matching `.zip.sha256`, `DELIVERY-0.11.0-published-a216747.json`, `LATEST.json` and `README-LATEST.md` are beside it. `DELIVERY.json` inside the folder records all payload hashes except its own. The ZIP was integrity-checked, every entry was compared with the ready-to-use folder, and the backend's executable permission was verified in the archive. Earlier deliveries remain unchanged.

The backend is `backend/native-macos-arm64/dosbox-x`, SHA-256 `0876e686d6a85f8c1b790db03314b81f471f5a5791dcad4929b90b63a1ebeced`. It supports both ordinary debugging and code layers. It uses the libraries already installed on the tested Mac; it is not a portable runtime for arbitrary hosts. Other hosts should build the complete layers patch against DOSBox-X `029bd65c5dcc7cdc7f2e14e35278620d9707d969`. Native checkpoints require an exact compatible backend/profile and matching mounted inputs; do not assume compatibility with 0.10.0 checkpoints.

Verification: ordinary Linux **759 passed, 28 skipped**; the [native Linux matrix](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891475) passed **15 established-backend tests and 32 layers-backend tests**, with no native skips. The published wheel passed **32 focused native tests** on this Mac; the copied wheel/backend pair then passed the **two compatible-checkpoint/restart and marked-click tests**. The complete Mac suite retains its documented Linux ELF fixture/toolchain limitations.

Original game files, in-game saves, native saved states and local project databases are excluded from the public packages and local delivery. Tests used temporary private inputs outside the delivery. The Python packages contain no emulator. The separately supplied backend retains its upstream GPL notices.
