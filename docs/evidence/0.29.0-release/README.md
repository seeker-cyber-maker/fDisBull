# 0.29.0 release-candidate evidence

Candidate source: `release/0.29.0` at `0844127c266280ed466f777c47af3470b129a8e1`
(tree `f28134c0c2f47a3df290d11f1ce500a88d8177f8`). Evidence is recorded on
the same branch in this directory.
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

## Qualification

- Focused world-model suite: **8 passed**.
- Full macOS suite: **2,596 passed, 127 skipped, 3 failed, 23 errors** in 108.57s.
- The three failures were reproduced exactly at the 0.28.0 base:
  a Linux ELF expectation on macOS, a GCC ELF fixture build, and a
  case-sensitive `VOL.2`/`vol.2` media fixture.
- The 23 errors are Linux ELF/GCC fixture builds on this macOS host.
- Local Apple Linux container, `linux/amd64` under Rosetta, Debian 13,
  Python 3.13.18, Node 20.19.2, GCC 14.2.0:
  **2,593 passed, 156 skipped, 0 failed, 0 errors** in 156.39s.
- Wheel: `fdisbull-0.29.0-py3-none-any.whl`,
  SHA-256 `4642cbafad4860dc0abb2602237ad84f471fccd167e6e2e0fdc008cd567aaebd`.
- Source distribution: `fdisbull-0.29.0.tar.gz`,
  SHA-256 `9a8f1015fcf65ecb49d024f04350b56e023fdf0af909a27376eeeb078cf57302`.
- `check_dist.py`: wheel 196 tool-only entries; sdist 708.
- Installed-wheel smoke: `fdisbull --version` reports `0.29.0`; `capabilities`
  loads and reports the packaged runtime version.

## Limits

This packet is local host evidence. The Linux result comes from a local Apple
container, not hosted Linux CI. It does not supply native backend rebuilds,
installed-wheel acceptance on a fresh shared prefix, a Git tag, a
GitLab/GitHub release, or a publication claim. The macOS three failures and 23
errors remain environment-specific and must be resolved or explicitly accepted
by the remaining release gates.
