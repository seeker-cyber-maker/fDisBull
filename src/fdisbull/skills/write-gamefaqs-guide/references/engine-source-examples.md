# External engine and format examples

**External game facts: check the information policy before reading further.**
These examples belong to reference-guided investigation or a permitted later
comparison. A files-only recovery pass should use the general format-writing
reference and supplied target evidence without opening this file. Keep any
subsequent comparison distinct from independent recovery.

## Contents

- [External engine identity](#external-engine-identity)
- [Resource layout examples](#resource-layout-examples)
- [Related-edition examples](#related-edition-examples)
- [Primary-source examples](#primary-source-examples)

## External engine identity

ScummVM's documentation describes replacement of shipped executables [E01].
Supporting a game in that project does not establish that its code is embedded
in the original. A source reader's behavior and original target correspondence
are separate claims.

## Resource layout examples

At pinned ScummVM revision [E02], the ordinary AGI v2 loader reads separate
resource directories in three-byte entries. The upper nibble selects a volume;
the remaining 20 bits form a big-endian volume-file offset. Its ordinary resource
header is five bytes: signature at 0, volume/flags at 2 and a little-endian
16-bit payload size at 3. These are observations about that external reader,
not a new extraction from any supplied game.

The v3 loader [E03] instead reads four little-endian directory offsets from an
eight-byte prefix and reads seven-byte resource headers with separate decoded
and stored sizes. It distinguishes picture handling from general decompression.
The v2 implementation also handles specific mixed-layout cases. Consequently a
filename, shared title or engine-family label is insufficient to select every
layout rule. This is an illustrative index/header comparison, not a complete
AGI specification or proof that all payloads share one encoding.

## Related-edition examples

The following are external-source examples of candidate relationships, based on
the pinned detection and loader sources [E02-E05], not newly analyzed game files:

| Specific source/destination group | Candidate reusable work | Required limit |
| --- | --- | --- |
| DOS AGI editions such as KQ1 2.0F, SQ1 1.1A/2.2 and PQ1 2.0E/2.0G | Resource-directory concepts, selected payload decoders, and matching interpreter-opcode behavior. | Confirm actual resource and interpreter revisions independently; room IDs, flags, vocabulary, puzzles, timings and bugs remain game-specific. |
| KQ1 SCI remake (`kq1sci`) | General resource/VM investigation method; qualified SCI-family tooling. | Pinned SCI source groups this title under SCI01, separately from AGI; do not apply AGI layouts or opcode numbers. |
| SQ1 and PQ1 SCI remakes (`sq1sci`, `pq1sci`) | SCI-family resource/VM hypotheses, after matching profiles. | Pinned source groups these under SCI1; that alone does not prove identical resource variants, native semantics or scripts. |
| Early KQ1 booters, non-DOS ports, fan remakes or translations | Findings whose precise file/runtime correspondence is independently established. | Do not fold these into the DOS AGI-v2 example from title or appearance. Detection records include distinct early KQ1 cases. |

Detection metadata may select a compatibility profile instead of literally
reporting the original executable version: the pinned PQ1 records, for example,
contain comments about historical interpreter versions alongside different
configured compatibility values [E04]. Retain both meanings rather than turning
one field into a verified binary identity.

## Primary-source examples

Inspected **2026-10-30**. These sources motivate the writing requirements and
edition examples; they do not certify a supplied game's bytes or behavior.
ScummVM source was read directly through GitHub at pinned commit
`7a21ad63f8c5c0456474d007d25dae230eafd905`; no original game was executed here.

- **E01:** [ScummVM documentation, v2026.4.0 introduction](https://docs.scummvm.org/en/v2026.4.0/index.html).
  Its description of replacement executables motivates keeping external engines
  separate from recovered original code.
- **E02:** [AGI v2 loader](https://github.com/scummvm/scummvm/blob/7a21ad63f8c5c0456474d007d25dae230eafd905/engines/agi/loader_v2.cpp),
  `loadDir`, `loadDirs`, `loadVolumeResource` and `detectV3VolumeFormat`.
  Explicit field widths/bases and mixed-layout handling motivate scoped specs.
- **E03:** [AGI v3 loader](https://github.com/scummvm/scummvm/blob/7a21ad63f8c5c0456474d007d25dae230eafd905/engines/agi/loader_v3.cpp),
  `loadDirs` and `loadVolumeResource`. Directory/header and payload handling
  differ from the ordinary v2 path; a shared family is not a universal profile.
- **E04:** [AGI detection table](https://github.com/scummvm/scummvm/blob/7a21ad63f8c5c0456474d007d25dae230eafd905/engines/agi/detection_tables.h),
  KQ1, PQ1 and SQ1 records. Distinct releases/platforms and compatibility values
  motivate exact-edition transfer claims and separate executable identity.
- **E05:** [SCI game descriptions](https://github.com/scummvm/scummvm/blob/7a21ad63f8c5c0456474d007d25dae230eafd905/engines/sci/detection.cpp),
  `s_sciGameTitles`. Separate remake IDs and SCI-generation groupings
  motivate checking engine families before transferring a decoder or rule.
