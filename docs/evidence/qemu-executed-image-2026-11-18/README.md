# QEMU executing-image and checkpoint identity

The [verification receipt](verification.json) pins the separately reviewed source, executing images and exact tests. The implementation is described in [the identity contract](../../QEMU_EXECUTED_IMAGE_IDENTITY.md).

Identical launch scripts and version strings previously hid distinct native producers. The new top-level runtime component measures the OS-observed main image of the exact QMP process, retaining the original launcher for relaunch. A fresh destination is checked before state import. Legacy states without this evidence refuse explicitly.

All seven final Linux native cases pass: the changed-producer negative controls preserve the healthy original stopped owner and refuse before import; six SB16/OPL hot and separate-Python cold cases retain same-producer continuation. Known native owners are reaped. The broad host set passes 3,590 cases with 499 intentionally unexecuted native cases; the independent review passes 49 focused checks, and the final root integration with movement/RAM/spatial policy passes 166. These counts overlap.

Independent review found and fixed missing Wine cold-constructor and DOSBox-in-QEMU timeline callers, a Darwin cleanup exception path, a Linux no-pidfd signaling fallback, and transport-close failure skipping Popen reap. Failed reproductions remain preserved.

A frozen helper first passed real macOS mapped-vnode/open-descriptor/hash and QMP-process checks on the corrected signed binary without advancing the guest. The subsequent installed-package gate at integration commit `6473b808` passes eight actual native cases: the changed-producer negative control, all five SB16 variants (including the auxiliary silence timer), and both OPL cases. Two identical launch scripts execute the separately preserved signed old and corrected images. All 720 production files match source, wheel and installed package. Runtime payload, test files and 98 pinned dependencies remain unchanged, with no unexpected or remaining owned processes. The selection's estimated count was seven; the retained XML and runner receipt record the actual eight collected cases, with zero failures, errors or skips. No rerun or changed assertion was needed.

Shared-library closure, unknown forwarding descendants, the documented Darwin signaling race and standalone CHIP-8 remain outside this guarantee.
