# 0.29.0 release-candidate evidence

Candidate source: `release/0.29.0` at `0844127c266280ed466f777c47af3470b129a8e1`
(tree `f28134c0c2f47a3df290d11f1ce500a88d8177f8`), followed by evidence and
artifact rebuild commits on the same branch. The rebuilt wheel has the same
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

## Limits

This packet is local host evidence. The Linux result comes from a local Apple
container, not hosted Linux CI. The dependency bundle is reusable evidence,
but the full native offline kit remains pending because the DOSBox-X overlay
changed after 0.26.1. This packet does not supply native backend rebuilds,
installed-wheel acceptance on a fresh shared prefix, a Git tag, a
GitLab/GitHub release, or a publication claim. The macOS three failures and 23
errors remain environment-specific and must be resolved or explicitly accepted
by the remaining release gates.
