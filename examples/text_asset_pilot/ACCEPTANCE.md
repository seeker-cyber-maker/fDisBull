# Text asset pilot: local acceptance, 4 November 2026

## Scope and source identities

Actual Linux x86-64 runs with Python 3.13.5, fDisBull 0.31.1 and its matching
player. The owned input was Zork I release 88, serial 840726, Z-machine v3.
Original story SHA-256:
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.

The story and its game-derived products remain outside Git. No game
text, original bytes, screenshots, saves or transcripts are published here.

The compiler, decoder and unchanged reference runtime match the main-branch
Git blobs at base `242e5343f5aa55dec95af3a49668a71ae14982c6`:

| Reused file | Git blob |
| --- | --- |
| `src/fdisbull/zork_uil.py` | `f59d4594dc3ae35d87b4c1a9f367e8bf52e57aea` |
| `src/fdisbull/zmachine.py` | `e6feb76d21ec7c8e9360a0232a729c16b280ad51` |
| `player/fdisbull_player/word16.py` | `dac6c147a4ebfc7a18a97481f87da287d81ea99e` |

The six implementation/test/documentation files at
`08a73f94a914138eb1dff8f1c7a96d4ebf24e8ec` were checked against their live GitLab
blob identities after upload. The tests and native-process acceptance described
below ran on those same source bytes. This receipt is documentation-only.

## Measured results

| Check | Observed result |
| --- | --- |
| New authored positive/negative tests | 31 passed |
| Existing Zork UIL, Z-machine and Zork CLI tests | 44 passed |
| Real command sequence | 32 commands plus initial startup |
| Compared boundaries | 33 output/event and complete runtime-state matches |
| Isolated terminal and JSON-lines products | Both completed; normalized transcripts equal |
| Cross-shell save/restore | Terminal prefix checkpoint restored in a fresh JSON-lines process; final state matched |
| Repeated package build | Byte-identical |
| Repeated build per shell | Byte-identical |
| Original story after recovery | Unchanged SHA-256 |

The route includes input/parser handling, inventory, movement, object interaction,
modeled game SAVE/RESTORE, an unknown command, score/status, and confirmed quit.
The full command list is in the private acceptance archive rather than public
source. The test is bounded; no all-path or full-score playthrough is claimed.

## Media and product counts

- 2,150 static text bindings, deduplicated into 1,796 unique UTF-8 payloads.
- 1,800 total typed assets including the reference die, memory, index and receipt.
- Seven invalid static text candidates were rejected, not presented as verified.
- On the real route: 162 asset hits and 18 top-level legacy-codec fallbacks.
- The 18 fallbacks caused 68 legacy decoder invocations including abbreviation
  recursion. No dependency bytes changed on that route.
- Strict mode is implemented and tested on authored fixtures. It is not claimed
  to accept the complete real route, which still requires fallback.

| Product | Bytes | SHA-256 |
| --- | ---: | --- |
| Portable package | 2,902,485 | `89ab35de2163a1b7725dc1cd05aaaa3b015e5206a329872636d0bfb1740481b7` |
| Terminal Python application | 2,992,013 | `4a27178f1a57310c9671fe3aa16a6c9d19fac5696a0bac09e27c59775afbe3a7` |
| JSON-lines Python application | 2,991,998 | `cd0a2ea0174925319320a3adec95fd71ef93c112edb8931a03a27ac345090547` |

Both shell runs and fresh-process restore ended with complete snapshot SHA-256
`de6b0cc85ddfa16680954ac20d884234e12be9d40ec6ba58c8a44e746b10d16e`.
The package identity is identical across shell builds; their link identities differ.

## What these checks establish

This qualifies the new asset/provider/package seam against the unchanged shipped
word16 model, and the selected host realizations against each other. It checks
full snapshots rather than only displayed score or room text. Negative fixtures
cover damaged archives, unsupported format/compression, unsafe members, dependency
failures, missing/incompatible pins, changed text and abbreviation data, memory
output streams, package-mismatched checkpoints and game-output Git boundaries.

## What remains unqualified

- No independent original DOS interpreter, Frotz or whole-game comparison ran
  during this pilot. The original-to-word16 edge is not newly qualified here.
- These outputs are standalone Python ZIP applications, not machine-native ELF.
- The existing word16 IR, original-derived memory and source binding adapter
  remain. This is not full game-intent UIL recovery or source-data elimination.
- All-path text closure and removal of the residual codec remain unfinished.
- Image, picture-composition, animation and audio providers are not implemented.
- Hosted CI, release packaging gates, merging and publication were not requested.
  Source commits use `[skip ci]`; these are local checks, not hosted qualification.

Several early long command invocations were interrupted by host tool time limits.
The final harness separates recovery and product verification into completed,
reaped processes. Interrupted attempts are not counted as successful tests.
