# Source-bound isolated Amiga v2 runtime

The optional `amiga-v2-isolated` profile executes bounded resource operations,
cutscene entry, and cursor/control changes against a verified immutable byte
bank. It declares exactly one active global script and no other running script
slots or queued sentences. Variables, room, camera and controls begin at zero.
This is a reproducible analysis context, **not authentic game boot state**.

Default raw-script execution retains its earlier closed behavior. Select this
profile explicitly with a startup resource manifest. Version 0/1 machines cannot
use it. Script switching, room transitions, end-cutscene, verbs, rendering and
audio remain outside the profile.

## Prepare and run

Use private directories outside the checkout. Both output directories must be
new and disjoint; the runtime directory must not traverse symlinks or `..`.

```sh
python3 native/qemu-scumm/intake.py /private/game.zip /private/new-intake \
  --runtime-output /private/new-runtime --runtime-script 1

/private/build/qemu-system-scumm \
  -M scumm-test,version=2,resource-manifest=/private/new-runtime/manifest.json \
  -kernel /private/new-intake/scripts/001.bin -accel tcg,thread=single \
  -S -display none -serial none -monitor none -nodefaults -no-user-config \
  -qmp stdio
```

The input is the uploaded Amiga ZIP containing OFS ADF disks. Original payloads
stay outside Git and public source/review attachments.

## Bank admission and identity

`manifest.json` uses schema `fdisbull-scumm-v2-resources-1`:

| Field | Meaning |
| --- | --- |
| `profile` | Exactly `amiga-v2-isolated` |
| `source_receipt_sha256` | SHA-256 of the ordinary intake receipt |
| `script_id` | Selected global script, 1..255, present in its declared table |
| `code_sha256` | SHA-256 of the raw `-kernel` code view |
| `counts` | Declared slot counts for `costume`, `room`, `script`, `sound` |
| `resources` | Entries with `type`, `id`, `size`, `sha256`, and relative `path` |

Intake also records archive/index identity, exact directory ranges/digests,
source LFL/ADF origins, offsets and encoded-span hashes. Native admission
validates the catalog and every supplied payload; it does not independently
parse the original ADF or authenticate a publisher. The receipt digest remains
a provenance assertion bound into the manifest identity.

Each payload is the whole decoded old-bundle span. Its first two bytes are its
little-endian length; bytes 2 and 3 are opaque. A script's code begins after that
four-byte header. Native admission checks both the code digest and exact equality
between the selected resource's code view and the kernel. Loading another script
resource cannot replace the active code.

A room resource is the bounded prefix of its corresponding nonzero LFL, not
the entire LFL. Trailing script/costume/sound bytes are excluded. Room directory
selectors describe disk resolution; they are not the containing LFL IDs used by
other resource tables. Index 00.LFL, unresolved room-zero fallbacks and mapper
IDs above 127 are not materialized as rooms.

Admission stages the complete bank before publishing it. It refuses bad hashes,
lengths, duplicate slots, out-of-range IDs, missing selected code, unsafe paths,
symlinks and non-regular files. Descriptor-relative reads use `O_NOFOLLOW`; a
FIFO cannot hang before the regular-file check. Limits are 2 MiB of manifest,
256 slots per type, 1,024 entries, 4..65,535 bytes per resource and 64 MiB of
retained payload. There is no live bank replacement. Later source-file changes
cannot alter retained bytes or identity.

## Resource effects

Commands `0c`/`8c` carry a byte/variable resource ID and literal command byte.
A variable ID retains its full value. The high nibble selects costume (2), room
(3), script (5), or sound (6). Unknown kinds or zero low nibble are defined no-ops.

| Low nibble | Effect |
| --- | --- |
| 1 | Mark verified available bytes logically resident |
| Other odd value | Lock the declared slot without loading it |
| Other even nonzero value | Unlock the declared slot without unloading it |

Availability, residency and locking are separate. The current script starts
resident; other retained bytes start logically nonresident. There is no
heap-pressure eviction. A declared slot can be locked without an available
payload. Loading ID zero is a no-op. Room loads above 127 require the unsupported
mapper before ordinary bounds checks. Missing bytes block without retirement.
Other invalid indices produce `S_BAD_RESOURCE` (fault 8), a stricter bounded
admission rule: the reference can warn and ignore some invalid lock requests.
No game-specific compatibility repairs are applied to original resource bytes.

## Cutscene and cursor effects

Entry saves interface/input state, cursor variable, room and camera mode. It
sets variable 21 to 200; hides interface/cursor/input; empties sentence count;
sets variable 26 from 38 and variables 27..29 to zero; and clears the override
pointer. It preserves the override script field and variable 5. Freezing other
scripts and stopping sentence script 2 operate on the declared empty set of
other slots. Entry from script 2 is refused because self-termination needs a
scheduler. Nested entry is refused, a restriction compared with the reference's
overwritten single saved record.

Cursor commands use an unsigned word. A nonzero low byte replaces variable 21;
zero preserves it. High-byte bits 0/3 select applying freeze/freeze-on, bits 1/4
select applying cursor/input visibility, and bit 2 applies interface visibility
from bits 5..7. Without its apply bit, a group leaves that state alone.

Accepted cursor/entry instructions increment `ui_revision` once. This records
invalidated UI state, **not rendered frames or reference-engine draw-call
counts**. End-cutscene remains blocked before restoration: v2 must follow ego,
which requires actor validation, camera bounds/position, potential room
transition and redraws. Equal saved/current room is insufficient. Script
start/stop/chain, verbs and other missing effects remain non-retiring boundaries.

## Stopped QMP state and reset

Read `scumm-runtime-json` on the CPU path from `query-cpus-fast`. Schema
`fdisbull-scumm-v2-runtime-1` exposes profile enablement, code/catalog/receipt
digests, script ID, counts, controls, block reason, and available/resident/locked
records. Absent unmodified slots are implicit in the counts. This read-only
getter requires the single CPU to be stopped and returns no payload bytes.

Each accepted effect retires once through the scalar core's accounting path.
A rejection does not advance PC or emit retirement. No generic acknowledge/skip
interface exists. The startup-bound bank requires no asynchronous completion
protocol in this slice. The existing optional, lossy trace owns no effects.

Both `scumm-restart=true` and QMP `system_reset` clear variables, controls,
cutscene state, residency/locks, counters and the journal. They retain the bank,
source identity and configured observation/budget controls, and mark only the
selected script resident again. Explicit CPU registration in QEMU's reset graph
fixes an earlier build that emitted RESET without invoking the unattached CPU's
reset hook. Tests require RESET plus cleared state. Successful harness runs
require normal child exit; forced teardown cannot quietly count as success.

## Verification

```sh
cc -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -g \
  native/qemu-scumm/overlay/target/scumm/early.c \
  native/qemu-scumm/test_runtime.c -o /private/scumm-runtime-test
ASAN_OPTIONS=detect_leaks=0 /private/scumm-runtime-test
python3 native/qemu-scumm/test_intake_runtime.py -v
python3 native/qemu-scumm/test_native.py \
  --qemu /private/build/qemu-system-scumm --output /private/native.json
python3 native/qemu-scumm/test_runtime_native.py \
  --qemu /private/build/qemu-system-scumm --output /private/runtime-native.json
```

There are 1,499 independent portable assertions and 11 authored OFS/index tests.
The native runtime suite checks effect budgets, locks versus residency, full
state invariance across 12 mask/capacity configurations, seven non-retiring
boundaries, both resets, immutable retained bytes, and 22 startup rejections
requiring clean validation exits. Existing native tests gain global reset checks
for versions 0/1/2, bringing that suite to 22 cases. LeakSanitizer cannot run
under this environment's ptrace instrumentation; ASan/UBSan remain enabled.

Private target probes are recorded separately. This isolated zero-state
context omits authentic game initialization. Original-engine equivalence,
original v0/v1 inputs, optional TCG plugins, complete rendering/audio, hosted CI
and release qualification remain pending. Reference facts are pinned in
[PROVENANCE.md](PROVENANCE.md).
