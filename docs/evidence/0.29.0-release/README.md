# 0.29.0 release-candidate evidence

Candidate source: `release/0.29.0` at `c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`,
with the local code cut built at `f8dff0c`; evidence and installation-check
commits follow on the same branch (evidence head `2ce9791`). The rebuilt wheel has the same
196 entries and bytes as the earlier wheel; its archive hash differs because it
was rebuilt. The source distribution has 712 tool-only entries. Hashes identify the local
artifact build at the tooling cut; the final tag must rebuild both archives from
the final tree and update this packet.
Base: `release/0.28.0` at `d06bffb6dce58de09021aaddfac36e46299ab4df`,
merged with `integration` at `b21b204` (clean merge).

## Files

| File | Contents |
| --- | --- |
| `record.json` | Machine-readable identities, test counts, artifact hashes and limits |
| `full-suite-macos.log` | Full macOS pytest run with `z3-solver` and `managed` extras available |
| `linux-container-full-suite.log` | Full suite in the local Apple Linux container |
| `linux-container-info.txt` | Container image, platform and toolchain identities |
| `base-0.28-three-failures.log` | Same three failing tests run at the 0.28.0 base |
| `check-dist.log` | `scripts/check_dist.py` result for the 0.29.0 wheel and sdist |
| `artifact-sha256.txt` | Wheel and source-distribution hashes |
| `deps-manifest.json` | Offline dependency fingerprint, constraints and wheel hashes |
| `deps-check.json` | Reuse comparison against the built dependency bundle |
| `deps-install.log` | Fresh no-index dependency install and Z3/import check |
| `offline-dependencies-sha256.txt` | Dependency archive hash |
| `offline-wheel-smoke.log` | Rebuilt 0.29.0 wheel installed into the offline dependency venv |
| `backend-build.log` | DOSBox-X heavy-debug build log from the pinned baseline and overlay |
| `backend-identity.json` | Backend hash, source commit, patch hash and upstream baseline |
| `source-companion.json` | Source companion builder result |
| `offline-kit-manifest.json` | Full kit source, backend, companion and seven-wheel hashes |
| `offline-kit-sha256.txt` | Full kit and source companion hashes |
| `offline-kit-install.log` | Python 3.13.5 no-index install of the full kit |
| `offline-kit-acceptance.json` | Installed-kit Z3, keyboard, memory, restore, player and restart acceptance |
| `native-focused.log` | Focused native debugger, DOS exit/COM, keyboard and ZIP tests using the rebuilt backend |
| `shared-prefix/staged-verification.json` | Fresh shared-prefix verifier result before activation |
| `shared-prefix/installed-qualification.xml` | Installed-package pytest receipt, 818 tests |
| `shared-prefix/installed-qualification.log` | Installed-package pytest log |
| `shared-prefix/installed-player-smoke.json` | Two-process installed player save/resume receipt |
| `shared-prefix/doctor-dos/receipt.json` | Installed DOSBox doctor |
| `shared-prefix/doctor-dos-qemu/receipt.json` | Installed DOS-in-QEMU doctor |
| `shared-prefix/doctor-wine/receipt.json` | Installed Wine-in-QEMU doctor |
| `shared-prefix/doctor-global-dos/receipt.json` | Global-alias DOSBox doctor after activation |
| `shared-prefix/activation-postflight.json` | Complete active-prefix verification |
| `shared-prefix/post-activation.json` | Selector, aliases, runtime, installation and global doctor facts |
| `shared-prefix/rollback-preflight.json` | Guarded rollback plan for 0.28.0 |

## Qualification

- Focused world-model suite: **8 passed**.
- Full macOS suite: **2,596 passed, 127 skipped, 3 failed, 23 errors** in 108.57s.
- The three failures were reproduced exactly at the 0.28.0 base:
  a Linux ELF expectation on macOS, a GCC ELF fixture build, and a
  case-sensitive `VOL.2`/`vol.2` media fixture.
- The 23 errors are Linux ELF/GCC fixture builds on this macOS host.
- Local Apple Linux container, `linux/amd64` under Rosetta, Debian 13,
  Python 3.13.18, Node 20.19.2, GCC 14.2.0:
  **2,600 passed, 156 skipped, 0 failed, 0 errors** in 251.48s.
- Wheel: `fdisbull-0.29.0-py3-none-any.whl`,
  SHA-256 `0fbebc6142ecdb686c924f3c3d6f8ad0f3ed20b1453f378a9c8156e2cca538f6`.
- Source distribution: `fdisbull-0.29.0.tar.gz`,
  SHA-256 `c839319fd153d9c2f6933afd9662a0c837889d2dc9a2fb80310e2c51d0ae65e8`.
- `check_dist.py`: wheel 196 tool-only entries; sdist 712.
- Installed-wheel smoke: `fdisbull --version` reports `0.29.0`; `capabilities`
  loads and reports the packaged runtime version.
- Linux x86-64 dependency bundle: five third-party wheels (Capstone, iced-x86,
  LIEF, Pillow 12.3.0, Z3 5.3.2.0), fingerprint
  `ea2a9ca41c8a06ffa2a0c3439b971c7952f1c5c0cd54df65159e732da6b588eb`,
  SHA-256 `e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.
  Fresh venv install passed; `check` reports `reuse` with all hashes intact.
  `build_offline_kit.py --dependency-bundle` merged it into a seven-wheel kit
  smoke build.
- Full native offline kit: DOSBox-X heavy-debug backend rebuilt from upstream
  `029bd65c` plus the 33-file layers overlay; backend
  `2db1c812d8af64bb5c71f5a1cc1466511ac6212a919cd3e70b82ef1b8c7b3471`, source
  companion `f9560466383cbb4a8e1096434889d7009ae9fcca4b0d2511c25f4d61ea95d118`,
  kit `b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f`.
  Python 3.13.5 no-index install passed; installed acceptance reports Z3
  equivalence/counterexample, BIOS keyboard, memory, screenshot, native
  restore, post-restore input, player resume and project restart all true.
- Focused native suite using the rebuilt backend: **60 passed, 0 failed** in
  45.05s across debugger, DOS guest exit/COM, keyboard and ZIP stream tests.
- Fresh shared prefix `/Users/Shared/fDisBull/releases/0.29.0-c03dc4f`:
  Python 3.13.18, core/player 0.29.0 with genuine decoding, managed-analysis and
  Z3 dependencies. Installed-package gate: **818 passed, 0 failed, 0 errors,
  0 skipped** in 119.56s. The complete 3,221-entry payload verified before and
  after activation; `current` selects it and `INSTALLATION.json` records
  `active_verified`.
- Installed doctors: DOSBox, DOS-in-QEMU and Wine-in-QEMU all passed with
  `native_state_restored: true`; the global DOSBox alias passed the same doctor.
- Installed player: two fresh processes restored `hall`/`key` state and
  preserved private checkpoint permissions. The global player alias loads.
- Rollback preflight reports a ready guarded path to
  `releases/0.28.0-d06bffb` with 3,195 entries; no rollback was applied.

## Limits

This packet is local host evidence. The Linux result comes from a local Apple
container, not hosted Linux CI. The full native kit was rebuilt and accepted
locally, but the hosted native test matrix has not been rerun. The shared
prefix was installed and activated on this macOS host; its backend was inherited
from the 0.28.0 prefix by an APFS clone. This packet does not supply a Git tag,
a GitLab/GitHub release, or a publication claim, and it does not establish
portability to another host. The macOS three failures and 23 errors remain
environment-specific and must be resolved or explicitly accepted by the
remaining release gates.
