# 0.26 development verification

The runtime/source cut for these checks is local commit
`ee8339c43344218241bbd0698d552a8ced59073a`, version `0.26.0.dev0`.
Later documentation/evidence additions do not replace that identity. This is
candidate verification, not release acceptance. Ordinary and complete
required-native Linux CI are still required on the final combined SHA before
main promotion or tagging. Neither publication nor a shared-system update is
part of this development turn.

## Reviewed intake

- PR #26: production head `8e9f27a` plus test-only lifecycle amendment
  `17bc7197b5416d87604ac8b91fc0abb0f8d4d93f`. The focused private review passed
  106 checks with one optional native skip. Service/main lifecycle tests use a
  simulated native boundary; they do not by themselves qualify the actual
  `run_session` recovery callback. Its separately reported installed-game
  acceptance remains bound to its original runtime.
- PR #28: `bfcdfe8eb5a030cb6f0e917067690fe2f7e4d03c`. Three integration
  conflicts were resolved by retaining both evidence additions and both the GOG
  and Z-machine standalone CLI methods. Independent private review passed 318
  overlapping new, preserved and package-facing tests. On qualified R88 input,
  1,788 reached candidates preserved raw decoder fields; 13 unresolved edges
  correctly left analysis partial. This static comparison is not gameplay.
- PR #30: `263998798d3d4d526e26a9130341c92613846d34`, including #29's ancestry.
  Both documentation CI runs passed. Original linked proposals and feedback
  retain their status and provenance.

## Fresh combined checks

| Check | Observed result and scope |
| --- | --- |
| Combined recovery, bridge, batch and Z-machine selection | 183 passed; raw log retained privately. |
| Candidate package/distribution/skill/recovery/processor selection | 196 passed. |
| Native DOS watch/doctor/debugger selection | 30 passed with required native backend. Includes the completed four-word and partial 8,192-word copies. |
| Full Mac source suite without optional native environment flags | 1,993 passed, 108 skipped, 2 failed, 23 setup errors. This run is not green. The same 25 unsuccessful identities occur in the retained 0.25 Mac source check; they are Linux ELF/GNU-linker fixtures on the Apple compiler. Identities are retained in the safe summary. |
| Core/player wheel, sdist and source ZIP at the source cut | All four archive guards passed. All 554 ZIP entries matched Git; RFC 0002 vectors/replay summary were present and byte-identical. |
| Private installed package resources | All 158 core and 9 player files matched wheels and source. Both installed skill gates passed, including 10 investigation files/27 links and 5 guide files/4 links. |

The installed skill probe used a private no-dependency environment. It proves
the projectless skill path and installed bytes, not a complete debugger
installation; genuine native/source tests used the existing shared Python and
dependencies without modifying that installation. No fake decoder modules were
used. The combined test counts above overlap and are not added together.

## REP regression

Before the fix, a real authored REP MOVSW stopped at the same instruction with
`CX=0x1ffc` of the original `0x2000` words still remaining. The old normalized
reply said `instruction_completed=true`. New unit/native regression tests
failed on that old contract before the fix. They pass with conservative unknown
completion. A four-word copy separately reaches zero count and the following
PC; the generic access hook still supplies no completion certificate.

The tested Mac backend SHA-256 is
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
This changes wrapper interpretation and the doctor contract; it does not
rewrite native records or modify the backend binary.

## Combined original-DinoPark recovery

A fresh private trial used the source cut above, the verified Mac backend and
the exact funded26k seed (`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`).
All 135 declared payloads and 65 loaded tool modules matched the archive. The
actual `run_session` callback recorded one injected post-action RuntimeError
and one incomplete reply with confirmed effects. The worker/guest identities
survived; following input was withheld. Two raw actions and a new save were
refused without changing the native input journal. Explicit checkpoint restore
matched all 20 fields before 100 guest milliseconds of input-free preparation,
requalified the scene, cleared recovery-only mode, issued a fresh token and
rejected the stale token. This rewind is an explicit intervention, not a claim
that an earlier purchase remains in the final rewound game state.

The service recorded completed cleanup and the native process exited zero;
no owned process remained at readback. The runner then failed in its final
audit writer because an inherited manifest lookup omitted the `src/` prefix.
The error trace was preserved and the existing evidence revalidated offline
with the correct mapping, without replaying the game. The worker exit code was
not recorded and remains unknown; `native_complete` remains false in the raw
phase record. This confirms the bounded functional recovery path, not an
overall runner pass. Original game and seed inventories remained unchanged.

## Remaining acceptance

Final source/archive checks must be refreshed after the evidence cut.
Exact final Linux ordinary/native CI remains pending. Full Mac source parity,
guest `.fdb` persistence, native/guest mapping, original-intent completion
certificates, and whole-game reconstruction are not established by these checks.
Native fatal/unreachable guest cases remain unqualified; controlled unit tests
are not substituted for those paths.

See the [safe summary](evidence/integration-026/verification.json) for source
identities and test classifications. Original games, saves, states, raw native
journals, generated story packages and project databases remain private.
