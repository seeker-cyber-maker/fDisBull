# KQ1 logic 103: native branch and dialogue qualification

The follow-up to PR #78 exercises the remaining logic-103 branches in the
original DOS interpreter and exports a small source-linked Z projection.
The input is still direct AGI bytecode; the native interpreter is the runtime
oracle for the selected model. No x86 disassembly is used as the story input.

## Reproduce the bounded native sweep

Supply the exact user-owned KQ1 edition and qualified DOSBox backend described
in [the host contract](AGI_DOS_HOST.md). Use a fresh private output directory:

```text
PYTHONPATH=src:. python examples/agi/verify_branch_coverage.py \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/kq1-native-coverage --dialogue-key enter
```

The runner prepares ten authored starting frames plus independent print and
erase probes in twelve fresh private game copies. Each first initialization
must finish before a new diagnostic call is admitted. Original source bytes
stay unchanged. The caller operand is restored before selected logic executes;
later callsite reentry checks the completed native frame. Scalar, position and
drawn-bit edits are logged explicitly. Drawn-bit edits do not establish sprite
rendering consistency or naturally reachable saves.

All **23 invocation receipts** completed with the declared final projection
matched. The sweep observed **111/111 source offsets, 56/56 object/resource
effect sites and 44/44 conditional outcomes**. Each conditional's actual next
source offset distinguishes its two outcomes. The count excludes incomplete
and interrupted trials. Branch coverage is not enumeration of all input
combinations, every predicate short circuit, every transient value or every
possible path.

`aggregate_native_coverage(projection, trials)` in `fdisbull.agi_coverage`
checks complete verified receipt status, matching resource and invocation
identity, source/attempt counts, native breakpoint evidence, effect opcodes,
graph transitions and original returns. Duplicate invocations, partial traces,
foreign resources and malformed data refuse. Conditions with identical
destinations remain unknown rather than counting both outcomes. The output
contains observed/expected counts and explicit missing sets.

The aggregator consumes caller-supplied records; it cannot authenticate a
native session from JSON. The qualification here comes from the separately
executed source-bound monitor, retained private traces, unchanged input
manifests, implementation hashes and authored replay script. A coverage count
alone is not an equivalence proof or a whole-game recovery result.

## Blocking dialogue

The sweep completed real blocking print operations at source offsets **375,
413 and 450**, using an explicit Enter policy. Separate fresh trials completed
Escape dismissal and original timed completion. Offsets are decimal bytes
from the selected logic's code start.

The key policy follows a bounded native sequence:

1. Verify the original RAM message bytes against the captured CP437 source
   message, recording its digest without exporting the text.
2. Stop at the original input wait, verify its native call frame and open-window
   flag, and require the keyboard queue to be idle.
3. Allow at least 50 measured guest milliseconds inside the wait, with owned
   source breakpoints guarding against unexpected continuation. Capture a
   newer completed frame with a stored artifact and an explicit matching video
   mode identity.
4. Re-enter and requalify the native wait, queue one physical Enter or Escape,
   then observe the original handler return, window closure and settled input.

Visible, ready and completed remain different observations. Frame freshness
does not replace the wait/stack/window checks. The port's `visual_verified`
flag remains false: the engine verifies source message identity and stored
frames, not OCR or pixel-by-pixel dialogue text. The selected waiting frame in
the [sanitized evidence](evidence/agi-branches-2026-10-31/receipt.json) was also
visually inspected during qualification.

Without `dialogue_key`, an untimed blocking print still stops incomplete and
requires reconciliation. Missing/stale artifacts, a short preview interval,
missing/invalid/changed mode identity, foreign stops, a changed message, pending
input, a lost key response or a window
that stays open cannot complete the operation. Every phase shares the original
per-step and total guest/wall budgets. Input attempts and prior completions
survive later failure; readback never sends another key.

## Separate Z content and player

The [Z-scene builder](AGI_Z_SCENES.md) uses source messages and checked native
receipts to build two independent goat diagnostic probes. It models the
observed object-13 drawn flag changing from true to false and refuses repeating
that departure action. The original messages and generated content remain in
the private output directory. Only the builder, tests, provenance/digests and
hash-only player receipt are committed.

The exported scene runs through the existing shared IL scene backend and the
separate text player. It is an authored partial projection, not an automatic
AGI-to-complete-game converter or a natural gameplay route. Its checkpoint
test covers in-memory save/load, not persistence across a fresh process.

## CI and version boundaries

PR #78 exact head `7922a1a81104f7211d492b2f7c9b633e4b6e38fd` passed its
[ordinary Linux workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41205770548)
with 2,291 tests and 118 skips. Its
[native workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41205770530)
passed stable (989 tests) and layers (1,307 tests). The dependent installed-wheel
job was cancelled after runner shutdown and exit 143 during runtime setup;
PE64/DOS/boot acceptance did not execute. The duplicate push job was also
cancelled. The job retry endpoint returned 404. A fresh dispatch of the same
workflow/ref was then rejected with HTTP 422, **"Actions has been disabled for
this user."** No restart was created. There was no observed failing source
assertion to patch, and full native CI remains incomplete.

The final selected local suite passed **400 tests**, with two skips, including
private-source Z/player checks and authored failure controls. The full macOS
suite completed with 2,296 passes, 121 skips, two failures and 23 setup errors.
Those failures/errors are Linux ELF/GCC fixtures receiving Mach-O or unsupported
Linux linker options from the Mac compiler; no AGI tests failed. The full local
suite is not green and does not replace Linux CI. Native
KQ1 qualification ran on macOS ARM64 with genuine CPython 3.13.13 and the pinned
installed DOSBox backend; it is separate from Linux CI.

The separately published [0.27.0 release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.27.0)
contains the partial static AGI inspector but excludes this open PR stack.
Its successful release CI is evidence for its own frozen commit, not for #78.
See the [feature history](FEATURE_HISTORY.md) for the shipped/reviewed distinction.
This follow-up does not merge, tag, publish or change an installation.
