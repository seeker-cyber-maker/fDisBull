# Direct Python block backend: local acceptance

Date: 4 November 2026. Linux x86-64, Python 3.13.5. Build-time front end and
reference oracle: supplied fDisBull 0.31.1 and matching player. Input: the user's
owned Zork I release 88, serial 840726, Z-machine v3, SHA-256
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.

## Generated output

- 55,891 candidate instruction-start blocks emitted as ordinary Python functions.
- 83 generated modules, loaded on demand.
- 7,680 candidate routine descriptors, retained for indirect-call coverage.
- 92 code/data files pinned by the product lock; 20,377,822 bytes including lock.
- `media.zip`: 2,150 static bindings and 1,796 unique UTF-8 strings.
- `memory.zip`: initial writable bytes, read-only backing and typed layout.
- Live memory export: dynamic bytes plus locals/frames/stack/PC, RNG, stream state,
  pending output/input and the modeled game-save slot. Exact asset/product binding.
- `_nodes`, `_expr`, generic `_library`, source instruction decoder and executable
  JSON node graph are absent from the product's execution path.

Candidate counts do not establish reachability. Code identities remain source
addresses; they are not recovered semantic function names. Services for parser,
object storage, streams, persistence and residual text decoding remain explicit.

## Local tests

15 new authored tests passed, alongside 31 previous package tests: **46 passed**.
The numeric test includes **7,216** successful arithmetic/comparison comparisons
and 176 divide-by-zero refusal subchecks. A separate unchanged Z-machine and Zork
regression selection passed **133 tests**. No hosted qualification is claimed.

Negative and boundary cases cover numeric wrapping and signed division/remainder,
global/byte-memory aliasing, object-attribute aliasing, control budgets, call and
indirect stack handling, memory-output text controls, abbreviation changes,
modified source-code guards, product tampering, asset-bound checkpoint refusal,
atomic invalid-state rejection, isolated process restore and deterministic builds.

## Actual game differential checks

| Route | Commands | Matched startup/command boundaries | Executed steps | Distinct Python blocks | Asset hits | Top-level codec fallback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Retained route, seed 12 | 32 | 33 | 23,465 | 1,205 | 162 | 18 |
| Forest/tree/window route, seed 44 | 31 | 32 | 29,195 | 1,466 | 137 | 29 |
| Restart/parser/failed-restore route, seed 879 | 21 | 22 | 11,371 | 931 | 102 | 4 |
| Total | 84 | 87 | 64,031 | Not additive | 401 | 51 |

Every boundary matched complete turn objects (including ordered events and
execution-step counts) and complete snapshots against the unchanged word16
reference. The full snapshot comparison includes random state, stack frames and
modeled SAVE state, not merely displayed score or location.

Each route's separate live-memory container restored into another runtime
instance exactly. A separate fresh-process test saved after the first 16 commands
of the retained route, resumed under `python -I`, and reached the same final
snapshot as uninterrupted execution. Both subprocesses exited successfully.

The compiler did not train on these routes: additional routes were chosen after
the product was built. Source bytes remained unchanged. No fresh original DOS or
Frotz interpreter comparison ran; the original-to-reference-model edge is not
newly qualified by these tests.

## Determinism and identity

Two fresh builds produced identical product locks and byte-identical contents
for all 92 locked files under the tested toolchain.

- Product lock: `2478a3defd883c36a19af2a5819772bf16fa555a375d99231bcfa3d274576721`
- Media: `f822a3c51f96266c42e10d1fbcdcda23a81c6ebc072962e97838caebd3a5bb34`
- Memory: `4fcca8c86e232135556a8d25fffe53b69276d922662b33d73637a2295506287d`
- Retained-route final state: `de6b0cc85ddfa16680954ac20d884234e12be9d40ec6ba58c8a44e746b10d16e`
- Forest-route final state: `5e1a8f8e4add9fb8fc01825561652fb600d78b6d151f04c4816bd8def8746560`
- Restart-route final state: `a415d710e028901d1da65ed0f5bcf5757fd649ef20e703bccc4fdc2585697a39`

## Retained failures and limitations

The first new-test run had six negative-test failures because the tests expected
the reference module's exception class rather than the generated support module's
separate class. The runtime correctly refused those inputs. Tests were corrected
to assert the generated class; semantic acceptance was not weakened.

The first expanded regression run had two fixture-layout failures: its CLI
subprocess could not locate the temporary source tree and one source-free test
could not locate the player file. Restoring the expected source/player test
layout fixed these; unchanged regression source then passed 133/133.

One combined build/test/verification shell call hit its host deadline before
verification completed. No receipt was produced and no process remained. The
final verification was rerun separately and completed. The exact final products,
not the intermediate build, produced the identities and results above.

This is mechanical Python translation, not whole-game intent recovery, native
ELF output, a complete playthrough, all-path proof or universal v3 qualification.
The 51 top-level text fallbacks across the three routes remain explicit. Read-only
backing retains source-derived code/text/data for guards and data reads; no source
opcodes are executed. Generated game programs, media, memory and private receipts
are excluded from Git and public source packages.
