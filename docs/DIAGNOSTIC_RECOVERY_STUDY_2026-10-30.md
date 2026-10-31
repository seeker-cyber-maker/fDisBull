# Diagnostic recovery beyond ordinary progression

Status: investigation-skill amendment and sanitized motivating findings,
30 October 2026. The baseline is main
`f94a5cd74b153b58f56c9fdb6c653d2e295f5ee6`; the private investigation used the
supplied fDisBull 0.26.0 package, not a newly installed main runtime. This change
adds no execution API, emulator capability, loader or canonical schema.

## Why the skill changes

The user's requested recovery includes routines absent from a new-game route.
Scenario selection, later saves, mutually exclusive branches, error paths,
unavailable environments and external modules make ordinary progression an
incomplete coverage strategy. The investigator should execute a bounded
original routine under explicit diagnostic preparations when that answers a
question, then recover the callers and state that could legitimately reach it.
A complete playthrough is not a prerequisite for knowing an asset decoder.

The new section in the existing packaged
[methodology](../src/fdisbull/skills/fdisbull-investigate/references/methodology.md#recover-behavior-beyond-ordinary-progression)
formalizes the following decisions. Its general procedure contains no external
game-specific facts, so a files-only experiment need not read this study.

| Requirement | Reason and motivating observation |
| --- | --- |
| Separate original instructions, host substrate, state preparation, effect boundary and ordinary reachability. | Executing a DOS game's instructions in a Linux compatibility context establishes neither DOS/4GW startup nor device behavior. |
| Pin a complete intervention recipe, bound execution and preserve originals. | An injected ABI, return sentinel, memory ranges and flags are part of the experimental input, not naturally observed state. |
| Retain faults and budget stops; do not automatically map zero memory or stub successful services. | A zero-count LOOP preparation and an invalid sprite destination exposed missing preconditions rather than shipping-game defects. |
| Use differential inputs and explicit negative controls. | The guarded selector remained 5 with disjoint state but reloaded 239 after a deliberately aliasing store; the old guard alone was insufficient. |
| Work backward into callers, loaders, registrations and alternate preparations. | A dynamic jump in the main executable dispatches to registered sound-service tables, including external LX modules. |
| Distinguish compression, inner format and original consumer behavior. | RNC integrity, sprite layout, normalized FLC decoding and actual original decompression provide different observations. |
| Keep evidence reuse efficient without weakening the conclusion. | Reuse mapped bytes and a qualified routine fixture; extend only the next caller/environment obligation instead of replaying unrelated gameplay. |
| Do not equate candidate decoding with runtime reachability or completeness. | The newly seeded case targets expand code coverage without proving that normal play selects every case. |

Existing one-controller ownership, explicit unknowns, resource/version checks,
source preservation and publication boundaries remain. Ordinary-interface
claims still require ordinary-interface evidence. Diagnostic results remain
useful under their stated domain even when that route is unavailable.

## Recorded target results

The exact original Syndicate MAIN.EXE is 518,713 bytes, SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
No original executable, asset, FDB, memory observation or raw disassembly is
included here. The findings extend the retained
[LE scope study](LE_WHOLE_BINARY_SCOPE_2026-10-30.md).

- Candidate decoding increased from **62,837 to 67,838 instructions**. Its byte
  union is **227,447 / 261,620 (86.94%)** of the executable object's extent,
  not the percentage of game logic recovered. All prior rows remained unchanged;
  all current encodings match mapped bytes and a separate decoder agrees on
  their recorded lengths. The TEST/STOSB overlap remains intact.
- Two external LX sound drivers have **19 and 38 service entries**. A private
  one-object/internal-offset32 mapper and separate candidate analysis expose
  **1,670 and 3,421 instructions**. This is not production LX support or driver
  execution; each driver retains its own address space and identity.
- All **284 named RNC1 resources**, representing **172 distinct compressed
  payloads**, pass the final reference-guided reader's length and two CRC checks.
  Original decompressor instructions returned byte-identical output for three
  real assets. In-place, changed-header-CRC and invalid-magic controls retain
  their distinct outcomes. Original validation does not inherit the external
  reader's stronger checks.
- Structural checks cover **9,992 sprite entries**, two different pixel
  encodings, **118 maps**, linked animation tables and sound-bank directories.
  The animation sprite field is a six-byte-aligned TAB displacement; treating
  it as an unscaled ordinal fails the actual table range.
- **50 movie paths / 5,153 frames** decode through an explicitly normalized FLC
  container. Two ending-movie copies retain an incomplete extra-frame tail;
  their 136-frame prefixes decode separately. Supplied normalization timing
  is not recovered timing or original playback equivalence.
- Nine sound banks contain **180 structurally checked VOC streams**, including
  duplicated content across releases and repeat-control blocks. No music
  truncation, device playback or full media completion contract is claimed.

The independent reference RNC decoder was adapted openly from
[FreeSynd](https://github.com/winterheart/freesynd/blob/b8c05e606d75fcd320ce02b584f4cc427799b110/src/utils/dernc.cpp),
with GPL attribution in the separately delivered research tools. Format research
also consulted [libsyndicate](https://icculus.org/libsyndicate/libsyndicate.html),
[FreeSynd graphics notes](https://freesynd.sourceforge.io/ff.php.html), and pinned
[innoextract](https://github.com/dscharrer/innoextract/tree/6e9e34ed0876014fdb46e684103ef8c3605e382e/src)
for installer metadata. This is reference-guided analysis, not blind recovery.

## Diagnostic substrate and limits

An authored 64-bit Linux helper maps private original regions and scratch/stack
state. Ptrace selects a 32-bit compatibility context and single-steps original
instructions, with finite step/wall/CPU limits, checked fetch boundaries,
explicit stops before unsupported services and owned-child cleanup. It is not
a DOS session, a general malicious-code sandbox, a new fDisBull backend or an
original machine snapshot. Sound drivers and the whole game were not executed.

The 130-case discovery matrix includes 81 returns, 30 selected pre-jump stops,
16 instruction-budget stops and three signals. A separate packaged-harness
regression re-executed **69 selected cases**: 65 returns, two pre-jump stops and
two expected diagnostic faults. Its 48 color/column cases and three original
RNC/reference comparisons matched again. These are not 130 independent feature
validations or ordinary player routes.

Preserved friction includes a rejected direct 32-bit ELF launcher, corrected
RNC terminal lookahead, a wrong graphics observation stride and the invalid
zero-count/sprite preparations. Two packaging receipt writers initially reused
older output paths, replacing those two raw generations with repeated results.
Captured first-run output remains; separate raw preservation of those two
generations is not claimed. Routing was corrected without changing target code.

## Skill-delivery verification and follow-up

This amendment modifies two existing packaged resources, so it adds no new
catalog entry or distribution inventory requirement. UTF-8, frontmatter,
heading/link closure, whitespace and exact selected-resource retrieval are
checked separately from the research results. The transport check uses a private
copy of the installed 0.26.0 package with only these two texts overlaid; it is
not a full main-source or native-runtime regression. No general agent-performance
speedup or new backend API is claimed.

Remaining original-game questions include three graphics caller/loop contracts,
runtime table mutation, full sprite-variant semantics, selected loaded driver
instances and mission records' player-visible meaning. Continue with the next
missing dependency and an explicit access hypothesis, not a blanket requirement
to finish normal play before recovering anything further.
