# Colonization food production: DOS and Windows counterparts

The parallel continuation found the Windows counterpart of the DOS center-food
production/cache routine. It also found a smaller helper-free kernel whose
source-derived food-output models agree over their complete declared input
domain. The surrounding machine state and runtime effects remain separate
qualification obligations.

This is an owned-input analysis. Original programs, retained-byte projects,
disassemblies and raw evidence remain private. The new [NE loading view](NE_LOADING.md)
lets the Windows program be analyzed through its actual segments rather than
manually imported raw projections. The proposed [snippet relationships and UDL
backing layers](uil-rfcs/0003-cross-edition-snippet-links.md) are a design follow-up,
not a new database feature or compiler selector in this PR.

## Source identities and locations

| Edition | Original SHA-256 |
| --- | --- |
| DOS VICEROY.EXE | `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3` |
| Windows COLONIZE.EXE | `ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650` |

| Boundary | DOS static CS:IP / source file | Windows logical NE location / source file |
| --- | --- | --- |
| Center-food procedure candidate | `15EB:1F72` / `0xA222` | `ne:4:0x547c` / `0xCA7C` |
| Helper-free terrain/mode kernel | `[15EB:1F97,15EB:1FFC)` / `[0xA247,0xA2AC)` | `[ne:4:0x54b5,ne:4:0x5531)` / `[0xCAB5,0xCB31)` |
| Food staging byte | DOS `DS:A891` | `DS:4852`, conditionally bound to declared DGROUP segment 33 |
| Mode input byte | DOS `DS:53A6` | logical NE segment 19, offset `0x76A2`, accessed through ES |
| Production cache | DOS `DS:8DC8` | logical NE segment 20, offset `0x0122` |
| Secondary signed index / yield byte | DOS `DS:A893` / `DS:A894` | `DS:4854` / `DS:4855`, conditionally DGROUP 33 |

DOS addresses above are static analysis contexts, not a promise of current
runtime placement. NE segment indices are decimal logical identities, not DOS
paragraphs or observed Windows selectors. The procedure prologue establishes DS=SS. Windows locals also require the
correct stack binding. The header's declared stack/autodata relationship is
static evidence; no live Windows DS/SS was observed.

## The smallest useful correspondence

The closed local comparison takes a signed 16-bit terrain classification and a
stable unsigned 8-bit mode, then observes the staged unsigned food byte at exit.
Both original slices use this priority:

| Terrain classification | Base food |
| --- | ---: |
| 24 | 0 |
| 1, 17 or 9 | 1 |
| 27, 28, or 8 through 23 after the preceding exceptions | 2 |
| All other signed 16-bit values, including negatives | 3 |

Mode 0 adds 2; mode 1 adds 1; other byte values add zero. The original code uses
two sequential mode comparisons. Stable input is therefore an explicit model
assumption, rather than an invented single atomic read. Both Windows mode
comparisons were independently checked as byte comparisons in the original
file. Terrain range branches use signed comparisons.

The DOS slice is 101 bytes with 35 native instruction facts; the Windows slice
is 124 bytes with 39. Every byte decoded within each span, neither contains a
call, and direct branch targets remain in the slice or at its exit. These are
source facts, not performance measurements or proof of source-model semantics.

Separate analysts authored a model from each source slice. The coordinator
checked both original-file identities and slice boundaries, then compared
**all 16,777,216 pairs** of raw 16-bit terrain and 8-bit mode inputs. Every
modeled food result agreed. The canonical output digest, ordered by terrain
word then mode byte, is:

`61ec6cf06de7de52077992e9bcf2df21f2647c786b61b56c516595e6dc35faaa`.

The earlier original-DOS observation at terrain 13/mode 0 produced food staging
2 + 2 = 4. Both models predict that result. Model equality over the declared
finite domain does not establish Windows execution, complete procedure equality
or equality of all native effects. The models share human interpretation and
native-decoder assumptions; they are not an automatic UDL lift or independent
processor oracle.

## Why the same result still needs adapters

The DOS kernel preserves general-purpose registers. The Windows local kernel
uses AX and ES to access the mode segment and clobbers them at this boundary.
Its terrain input is a stack local, while DOS receives the value in AX. Both
write different bound locations. Flags, timing, faults and intermediate-write
observations are outside the compared food-output model.

A correspondence edge can therefore admit the food-output relation while
refusing direct full-ABI substitution. A selectable backing needs explicit
input/output state bindings and a compatible preservation adapter, or a caller
contract that admits those clobbers. Segment fixup placeholders must be resolved
symbolically; their original immediate words are not observed live selectors.

The existing bounded DOS UDL lifter refuses branches and memory operations.
These source-derived models do not widen it. No UDC compilation of these food
slices or cross-edition machine-code substitution is claimed.

## Larger candidate relations and remaining dependencies

| Candidate relation | Evidence and current ceiling |
| --- | --- |
| Terrain/mode staging kernel | Full finite food-output equality of the two authored source models; ABI and Windows runtime remain separate |
| Resource and improvement bonuses | Related tests/helpers appear around both kernels; helper semantics and complete state/effect correspondence need qualification |
| Production-cache rebuild | Both clear 20 words and accumulate staged food into the first entry, with secondary signed-index/yield handling; full effect equivalence remains a candidate |
| Annual warehouse update | Earlier independent code checks support a 16-word stock loop and a shared partial colony record layout; this is distinct from the 20-entry scratch cache |
| Calendar update | Earlier DOS native and Windows static findings share a useful pattern; they do not establish whole-turn or whole-game parity |

Initialization phase is part of the state binding. Nine candidate yield bytes
across all 29 Windows initialized-file rows are zero; only one row equals the
captured post-initialization DOS memory. This does not show different gameplay
parameters: Windows runtime loading/initialization remains unresolved. The
base/mode kernel does not depend on that table. A snippet relation must not
silently transfer post-initialization DOS data into an unqualified Windows state.

The production cache also runs during colony redisplay. Its calculation is not
by itself a committed warehouse update or world-turn witness. The DOS free
production cycle and normal-turn stock writer are separately scoped evidence.

## Product implication

Retain these snippet relations as versioned, authored database edges, rather
than duplicating a name across projects. Store the precise contract domain,
source spans, state relation, qualifications, counterexamples and unresolved
adapters. A fixed UIL `staged_base_mode_food` operation could then select a DOS, Windows or authored
UDL backing when its target/runtime and boundary contracts are satisfied.

That enables a synthetic output profile with mixed implementations and explicit
lineage. Exact original reconstruction remains a different profile. Neither a
shorter source span nor these comparisons establishes which implementation is
faster; that needs measurement including adapters and orchestration.
