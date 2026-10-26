# 0.16.0 candidate verification

This page preserves the initial candidate evidence. Later acceptance for
[standalone DOS/waits](VERIFICATION-DOS-KNOWLEDGE.md) and
[guest keyboard input](VERIFICATION-GUEST-KEYBOARD.md) is recorded separately;
current promotion status is in [release status](RELEASE_STATUS.md).

This is local source-candidate verification based on main `e91879c`, not a
0.16.0 commit/tag or GitHub CI result. Runtime source files match the tested
89-entry wheel. The source distribution and tool ZIP are checked independently
for excluded game/state/database/runtime/compiled-target payloads.

The complete Mac run recorded **856 passed, 16 skipped, 2 failed and 23 setup
errors**. The two failures expect Linux ELF output from the host compiler; the
23 setup errors come from the GNU/Linux linkage fixture under Apple tools.
This is not a green full Mac suite. The [raw XML](evidence/0.16.0/mac-full.xml)
retains those failures. Real selected-vCPU/boot debugging passed seven checks;
the [machine receipt](evidence/0.16.0/machine.xml) preserves that separate scope.

The real DOS and Wine/QEMU runtime doctors both passed from the installed wheel.
Their receipts, genuine dependency details, backend identities, frame/click
images and traces are under [DOS](evidence/0.16.0/dos-doctor/receipt.json) and
[Wine](evidence/0.16.0/wine-doctor/receipt.json). Native save/restore and memory
readback are actual emulator operations. The Wine doctor compiled fixed shipped
source in the guest and required no supplied target binary. Old guest-resource
fingerprints were correctly refused during development; the accepted run uses
the rebuilt matching image. Native states and temporary projects are absent
from those evidence folders.

The [DinoPark replay driver](../examples/dinopark/verify_temporal.py) ran from new
states and a private copied game. It restored one execution breakpoint, eight
read watches and a once-hook with hit count zero. The same experiment observed
AX=7,500 for the original lookup and AX=5,000 for the execution layer while RAM
and the price table stayed original. Extra two-fetch traces stop at the actual
lookup: the original bytes fail the altered interpretation comparison; the
layered bytes match its instruction and `real:334b` context. DOS completion
remains unknown for the earlier fetch and pending for the final budget record.
This is not a completed-purchase or whole-version execution claim.

The [55 hashed evidence files](../examples/dinopark/evidence/temporal-0.16.0-2026-10-26/SHA256SUMS.json)
include the raw captures, original traces, derived views, fresh analyzed PNG/SVG
exports and the bounded analysis status. All 192 original and mounted input
files stayed unchanged; native processes were reaped. States and project DBs
remain outside Git. The earlier 0.15.0 sealed evidence is unchanged.

Thirteen new malformed-trial regression cases failed before the comparison
alignment fix and pass afterward. They cover extra records on either side,
memory address/length mismatch, screenshot step mismatch, trace semantics and
intermediate operation mismatch. This hardening result does not assert a
supported native route previously produced inconsistent lists.

The restricted-client [0.15.0 offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip)
and its [checksum](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip.sha256)
were published with explicit approval as additional assets on v0.14.0. Readback
verified SHA-256 `d493481b5404ae3cdc0707adaf5ea3bb554660593b08ed22c1e0c8926eba5e50`
and all 311 payload files. Existing release assets and the tag were unchanged.
The asset is the exact 0.15.0 CI candidate plus genuine offline dependencies and
the previously qualified statefix1 direct Linux backend; it does not contain the
0.16.0 source changes. Its [publication receipt](evidence/0.16.0/PUBLISHED-OFFLINE-015.json)
keeps this distinct from release promotion.

Offline Linux Python 3.13.5 verification passed **842 ordinary tests, 55 skipped**, and **84 installed-wheel native checks with no skips**. Both used genuine delivered dependencies without networking. The [separate Linux receipt](evidence/0.16.0-linux/ACCEPTANCE.json) includes the module path, exact tested-wheel hash and XML/logs. The installed-wheel Mac native gate also passed **84 checks without skips**; the Wine doctor passed separately from that same installed wheel.

The re-downloaded 0.15.0 kit verified all 311 files and installed/started correctly in that guest. Its first 60-check native run passed 59 and timed out while requesting 1,000 guest milliseconds with a 2,000 host-millisecond deadline. The API reported that timeout honestly. This earlier failure is retained in the Linux receipt; a fresh guest subsequently passed the same exact case **three times** and the complete **60-check native suite**, with no changes to the published asset or the two-second test deadline. The [retry receipts](evidence/0.16.0-followup/kit015-retry/native.xml) are separate from the retained first failure. This establishes a working copied installation while preserving the observed timing sensitivity under nested emulation. The external Pro/DeepSeek
environment has not been accessed or qualified by these local tests.

The installed-wheel [DOSBox-in-QEMU doctor](evidence/0.16.0-followup/dos-qemu-doctor/receipt.json) also passed all 13 checks, using a newly prepared runtime containing the corrected Linux backend. Its native restore, actual mouse coordinates, data watch, execution overlay, trace and offline promotion were exercised in the real Linux guest.
