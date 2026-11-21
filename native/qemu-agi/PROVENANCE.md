# Source provenance

The AGI target is an experimental addition authored on 2026-11-21 for the shared
fDisBull/DotBox development tree. It uses QEMU's GPL target/TCG interfaces and is
distributed under GPL-2.0-or-later, as marked in the native source files and
overlay application script. The upstream GNU GPL version 2 text is retained
verbatim in [COPYING.txt](COPYING.txt).

The pinned upstream input is QEMU **10.0.13**, archive
`qemu-10.0.13.tar.xz`, 141,718,608 bytes, SHA-256
`4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
Upstream project: <https://www.qemu.org/>; source:
<https://gitlab.com/qemu-project/qemu>.

The target/machine registration and CPU scaffold were informed by the retained
fDisBull CHIP-8 v1 experiment, at repository snapshot
`4749e6a128019dab5beac7932a5213be51ec82d9`, path
`native/qemu-chip8/qemu-10.0.13-fdisbull-chip8-tcg-v1.patch`, SHA-256
`81fdfca213e47439d2acadea0d05ddc1e3e810e732942e8bc35cd1e1e4101e69`.
The AGI target has its own instruction semantics, direct TCG lowering,
observation controls and QOM interface. Its architecture bit is 25, leaving
the retained CHIP-8 experiment's bit 24 separate. The overlay applies to the
clean pinned upstream tree; combined-target integration is not claimed.

AGI scalar/position expectations are grounded in the existing repository's
AGI 2.917 models and its independent raw-byte oracle. The scalar oracle cites
ScummVM commit `f7403b6efaae2f033e8abea80b3fb6bee5303369`,
`engines/agi/op_test.cpp`, for the unsigned IF displacement and signed GOTO
distinction. The native tests do not use the production decoder to manufacture
their expected outcomes. Native fixtures and benchmark loops are authored
byte sequences, containing no commercial/private game resources.

`source-manifest.json` binds the native input files. Runtime evidence separately
binds compiler/dependency configuration, the applied source, the produced
binary and its actual tests. These identities establish the scope of a local
experiment; they do not establish original-game or backend parity.
