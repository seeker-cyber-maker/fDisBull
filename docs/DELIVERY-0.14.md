# Published 0.14.0 DeepSeek delivery — 2026-10-25

The [GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.14.0)
is published, not draft or prerelease, and targets
`6a0aeb3830eb544cd744d3410881c1c951a5ffb7`. Its five assets are the unchanged
tag-CI wheel, source archive and tool ZIP, plus `SHA256SUMS` and
`VERIFICATION-0.14.0.json`. All five were downloaded again and checked against
the original CI files, sizes and GitHub SHA-256 digests. The fixed tag and
package bytes are unchanged by this later publication record.

[Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623197)
passed **817 tests, 45 skipped** and audited all packages.
[Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623209)
passed **15 stable DOS, 38 layers/endpoint, 14 PE64 and 10 DOS/QEMU/boot checks**,
with no native skips. Both workflows also passed before tagging. All **84 wheel
entry contents** match the ordinary and native-tested wheel. Distribution audits
passed for 84 wheel, 206 tool ZIP and 214 source archive entries.

## Delivered folders

The user-designated full delivery is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.14.0-6a0aeb3/
```

It contains the exact published packages and wheel extraction, native Mac
ARM64 DOSBox and QEMU 11.1.2 with selected firmware, the tag-CI Linux DOSBox
executable, kernel and three pristine DOS/Wine/optional-IDA boot filesystems.
These boot filesystems are prepared runtime inputs, not saved target sessions.
All three passed complete member/resource exclusion audits. Mac QEMU needs
this Mac's existing Homebrew libraries, which are recorded in provenance and
are not bundled. The vendor IDA server and keys remain private user inputs.

The smaller direct Linux/DOS kit is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-linux-dos-offline-0.14.0-6a0aeb3/
```

It contains the same published tool and genuine offline dependency wheels,
the unchanged tag-CI DOSBox ELF and 63 private loader/shared libraries including
SDL2_net. It does not include QEMU or the boot filesystems. The private wrapper
does not replace system libraries. All copied operational files are byte-identical
to the full delivery. The dependency set includes Linux x86-64 Python 3.12/3.13
and Mac ARM64 Python 3.13 wheels; actual clean tests used Linux 3.13.5 and Mac
3.13.14. The Mac iced-x86 wheel is a genuine local build from the hash-verified
upstream source, with source/build provenance included.

From either ready folder, create a separate environment outside the delivery:

```bash
/opt/pyvenv/bin/python3 VERIFY-DELIVERY.py
/opt/pyvenv/bin/python3 INSTALL-OFFLINE.py --venv ../fdisbull-014-venv --with-tests
../fdisbull-014-venv/bin/fdisbull --help
../fdisbull-014-venv/bin/python fdisbull_delivery.py
```

Use the available Python 3.13 interpreter on Mac in place of the reported
Linux interpreter path. The installer uses only delivered hash-locked wheels
and refuses an existing destination. `fdisbull_delivery.activate()` selects
the extracted published tool from a fresh Python process. `dos_options()`
selects the correct native Mac or private-library Linux backend. Full-delivery
helpers additionally expose DOS/QEMU, custom Wine, optional IDA and raw machine
profiles. Original games, private databases and state sidecars belong outside
the sealed delivery folder.

## Fresh acceptance and the additional Linux limit

The copied Mac package/backend pairs passed **48 DOS/boot checks**, **4 optional
IDA checks**, and a **222.79-second custom Wine smoke**. The Wine smoke exercised
read/write watches, self-CRC with RAM and execution layers, branch toggling,
checked memory/full-width RAX edits, screenshots, marked clicks, traces and
fresh-VM checkpoint restoration. It used one private checkpoint; full native
fork/export acceptance remains in tag CI. A separate clean Mac offline
installation passed **51 checks with no skips**.

The independent network-disabled Linux x86-64 **CPython 3.13.5** probe passed
offline installation, actual CLI help/PE inspection, real ARM64 and DOS decoding,
PE parsing and private library resolution. Its native suite reported **49 passed,
2 failed, no skips**. The failures were native DOS state restores with a bad CRC
in the ZIP `Vga` record. They reproduced with the raw tag-CI ELF and system
libraries; CPU-profile and compression experiments did not resolve them.
**Native-state restoration is not qualified in this additional Mac-hosted
QEMU/TCG probe.** Its failed receipts are preserved. No invalid state was
rewritten or accepted to manufacture a passing result.

The original Linux tag-CI and accepted Mac results are distinct scopes. The
external DeepSeek `/opt/pyvenv/bin/python3` environment was reported by the user;
it was not accessed, changed or verified here. The offline kit addresses its
reported dependency gap, but that actual installation still requires local
verification. For state-dependent work, use the separately qualified Mac backend
until the additional Linux result is resolved or validated locally.

## Integrity and exclusions

The full folder has **437 payload files**, the compact kit **316**, excluding
each `DELIVERY.json` itself. Both standalone directory verifiers passed.
Every sibling ZIP passed CRC, per-entry SHA-256, exclusion and executable-mode
readback checks. `LATEST.json` and `README-LATEST.md` were updated only after
both bundles passed. Earlier deliveries remain untouched.

`fdisbull-unified-debugger-0.14.0-published-2026-10-25-6a0aeb3.zip`

- Size: 2117467790 bytes.
- SHA-256: `b0f437162fcba22a23703a3a57b88ecd781c30507a24f0d87243b860a935a759`.
- Manifest SHA-256: `307b1868b9b433ab6ac54c577221b8be2eb8af298d8616a2eb4b63b13dbc8f4f`.

`fdisbull-linux-dos-offline-0.14.0-6a0aeb3.zip`

- Size: 98555019 bytes.
- SHA-256: `8adef6ec336a1a9efb43695479bbbc38bca63e8ccfc9b5e38b4f59a825bc1868`.
- Manifest SHA-256: `04507ca7a4221a8043a14d0022e6de3337afae7e7869f93690c2c25d301315f9`.

Game files, in-game saves, captured emulator/native states, project databases,
compiled target fixtures, vendor server and keys are excluded from both delivery
folders and archives. Public Python packages also exclude emulator binaries and
runtime images. Exact-hash static OS/compiler `.state` support files inside the
pristine runtimes are identified by the runtime audits; they are not captured
emulator states.

Selected [publication and delivery evidence](../experimental/remote-debugger/evidence/2026-10-25-published-0.14/)
includes asset readback, CI metadata, copied-pair reports/screenshots/traces,
offline dependency/library provenance, failed Linux receipts and final delivery
receipts. No private state or database payload is retained there. Package docs
remain the fixed source-tag version; this later record describes publication
and local delivery without altering those package bytes.
