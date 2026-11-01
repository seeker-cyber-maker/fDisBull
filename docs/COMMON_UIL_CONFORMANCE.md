# Common UIL conformance and synthetic programs

The conformance example builds a new indexed program from a list of source
snippets, selects equivalent backings, and emits standalone Python and
JavaScript. It also imports a stock-flow calculation and bounded memory UIL.
The default inputs are authored public fixtures. Private game state and media
are optional external inputs and do not belong in this repository.

See [the common contract](COMMON_UIL_CONTRACT.md) for the representation and
[the example](../examples/uil_common/conformance.py) for executable construction.
The [conformance tests](../tests/test_common_uil_conformance.py) have independent
arithmetic and movement/raster expectations rather than treating the new
interpreter as its own oracle.

The authored implementation lives in
[`tests/fixtures_common_uil.py`](../tests/fixtures_common_uil.py); the example is
a thin checkout entry point. Tool-only test-source archives exclude examples
and retain that fixture, so the conformance suite remains runnable after
extraction. It can also be run directly as `python tests/fixtures_common_uil.py`
with the same arguments.

## A program that did not exist in a source binary

`synthetic_bundle()` starts with four bounded source specifications:

| Source | Declared meaning | Group |
| --- | --- | --- |
| x86-16 `INC AX` (`40`), flags explicitly unobserved | Add one to a uint16 port, wrapping | Increment |
| Restricted C `ax += 1;`, uint16 ports | Add one, wrapping | Increment |
| Python `ax = (ax + 1) & 65535` | Add one with an explicit width mask | Increment |
| Restricted C `ax += 2;` | Add two, wrapping | Separate behavior variant |

The three increment sources normalize to the same function and constants. Their
implementation identities and source languages remain distinct. This grouping
is exact normalized equality; it is not an algebraic equivalence proof. Plain
Python `ax += 1` has unbounded integer semantics and is refused by this importer.
The default assembly flags projection has additional observable outputs and
cannot silently join the projection with unobserved flags.

The example creates a new program with an indexed import, a new entry function,
and a separate helper function. The entry invokes the selected increment and
then calls the helper, which adds the presentation constant `7`. The result is
`(input + 8) mod 65536`. Neither the helper nor this composed program came from
those source snippets. Every source implementation is selected under the same
program and presentation, including inputs at wrap boundaries.

The orchestration plan selects an exact implementation identity for the import.
Typed shims copy the input into the callee and the result out. Each function has
its own frame: mutating the helper's input leaves the entry's original input
slot unchanged. The generated manifest preserves selected implementation,
source-language, source-assurance and shim information, together with artifact
hashes and the program/presentation/catalog/orchestration identities.

Selecting the add-two implementation under the increment semantic identity is
refused. A different RNG algorithm likewise represents an explicit behavior
variant, not an equivalent implementation merely because its ports match. This
contract does not automatically substitute related algorithms under one exact
semantic identity.

The Python and JavaScript outputs realize the selected common meaning as target
source. They do not execute the original C, Python, or x86 code through a foreign
ABI. The standalone programs consume JSON lines and require no fDisBull package
at runtime; actual source functions, branches and loops are emitted rather than
an embedded UIL interpreter.

## Food calculation

`food_legacy_program()` is an authored restatement of the public
`stock_flow.maintenance_contract()` statement list from the earlier web pilot
(`016ad75b854050110b02f3c96189c6a124ce5ae5`,
`src/fdisbull/stock_flow.py`). The imported computation is:

```text
new_stock = signed16(stock + produced - 2*population - supported*support_cost)
```

Stock, production, supported count and support cost are signed 16-bit ports;
population is a signed 8-bit port, widened before doubling. The common wrapper
explicitly requires support cost in `{1,2}`. That domain came from the outer
legacy contract; it was not a refusal encoded in the old statement list.

The deterministic input matrix is the public CivD food-swap pilot's 2,018
vectors: 1,250 combinations of signed boundaries, every signed-byte population
with both support costs (512 cases), and 256 fixed-seed cases. Tests compare the
common evaluator and both standalone outputs with a separately written integer
formula. The formula wraps only the final mathematical result; modulo-word
arithmetic makes that equivalent to the intermediate wrapping in the source
statement list. Overflow and negative population are exercised explicitly.
Invalid support costs refuse atomically.

This is a bounded scalar projection. These tests establish no new full-game,
end-turn, source-build, or original-CPU result on their own.

## Memory and graphics fixture

`mini_snake_program()` is an authored 64-word memory fixture with a 5 by 4 raster.
It is intentionally much smaller than the recovered Snake model. It covers
movement in four directions, boundary death, food/score updates, frame clearing,
and drawing a head and food index. The reference expectations use coordinate
arithmetic and a direct raster loop, independently of the imported UIL.

Tests exercise every board position, direction, and live/dead value, preserve an
unrelated sentinel word, and check owned output arrays. Additional memory
adapter tests exercise word index `69999` in a 70,000-word arena, wrapping,
comparison values represented as `0/1`, legacy shift-count masking, nonzero local
initialization and rollback after an out-of-bounds write. This checks the memory
interface without publishing a private game's font or initial state.

The fixture's raster is an indexed array, not an OS window. No keyboard/mouse
hardware or native rendering qualification follows from it.

## Deferred presentation

With `synthetic_bundle(host_effect=True)`, the entry requests an authored text
resource after computing the value. Both standalone outputs and the reference
runtime return `pending_host`, an event plan and `proposed_state`. Committed
state stays at the original input and outputs stay empty. No message box,
browser display or other host action is claimed to have occurred. A host must
validate and commit such a plan under the orchestration contract.

## Repeat the public qualification

From the checkout, with its Python dependencies and a local Node runtime:

```sh
PYTHONPATH=src:. python examples/uil_common/conformance.py \
  --output /absolute/private/new-common-uil-study
python -m pytest -q tests/test_common_uil_conformance.py
```

Choose a new output directory outside Git. The example refuses to overwrite an
existing directory. It writes generated programs and `conformance.json`, which
records artifact hashes, vector identities and the qualified edges. Use
`--python-only` when deliberately qualifying only Python. The tests mark the
JavaScript edge skipped if Node is absent; a skipped edge is not a pass.

## Optional earlier-evaluator and full Snake comparison

The example can compare against an explicitly selected earlier source checkout:

```sh
PYTHONPATH=src:. python examples/uil_common/conformance.py \
  --output /absolute/private/new-legacy-comparison \
  --legacy-root /absolute/path/to/earlier-fdisbull \
  --legacy-python /absolute/path/to/its/python \
  --snake-manifest /absolute/private/snake-comparison.json
```

`--legacy-root` launches the old scalar/memory evaluator in a separate process,
so current and earlier `fdisbull` packages cannot be confused in one Python
module cache. The report records the earlier checkout head and evaluator source
hashes. Food results must match the independent formula. This route does not
launch an emulator or an original game.

The optional Snake JSON contains `program` (the canonical legacy memory UIL)
and `initial` or `initial_words` (the exact unsigned-word array). Alternatively,
`initial_path` names an external JSON array, relative to the manifest or
absolute. An existing native-shell manifest that contains only `program` needs
a small private wrapper naming the separate initial file. The example checks
the exact word count; it does not shrink the arena or discard unused words.

The private run chains `reset`, `step`, and `render` when present. Each function
is imported under the common contract and compared over the entire arena with
the earlier memory evaluator. Python and JavaScript are emitted and executed
on those same prepared inputs. The receipt contains hashes and comparison
counts, not the initial array, font bytes, rendered frame or result arrays.
Generated artifacts and the wrapper remain private.

A fresh development run on 2026-11-01 passed the 2,018 earlier-evaluator food
comparisons. It also matched all 70,000 words after each retained Snake
`reset`, `step`, and `render`, including independently executed generated Python
and JavaScript. The common-runtime step counts were 1,821, 38 and 473,827. These
are three prepared model-function comparisons. They do not constitute a game
playthrough, original DOS CPU execution, native keyboard/mouse qualification or
an equivalence proof over all possible states.

The private development receipt is outside Git. Future source changes require a
fresh run; these dated results do not qualify an arbitrary later revision.

The final sanitized [verification receipt](evidence/common-uil-2026-11-01/verification.json)
binds the exact common contract, importer, runtime, generator and authored
fixture hashes. The final refresh includes all three selected source backings,
both standalone targets, full retained Snake functions and the native food gate.
It contains identities and counts, without private arrays or target bytes.

A separate fresh CPU gate also ran each identity-checked 36-byte food kernel
from the original 474.01, 474.03 and 474.05 executables through the isolated
x86-16 instruction provider. All 6,054 executions matched the new common
evaluator, independent formula and both standalone outputs. The source EXEs
and retained source databases stayed byte-identical; databases were opened
read-only. This qualifies those instructions and declared scalar adapters.
Retained DOSBox result files were hash checked as historical evidence; no new
DOS process or whole game was launched by this gate.

The adapter review also found and corrected a refusal mismatch: an unused
zero-initial local was granting an extra execution step. The memory importer
now reserves exactly the emitted initialization-prefix count, rejects a prefix
that cannot fit the common budget cap, and retains the original statement/loop
budget. The conformance suite includes a budget-one source that must roll back
its first store when a second store exhausts that budget.

A further private action study compared 31 prepared normalized-input cases
through the full retained Snake action function, the new common evaluator and
both standalone targets, over all 70,000 words. Cases cover ASCII/scan dispatch,
contradictory key pairs, pointer press/held/release/absent-device inputs,
pause/reset/single-step, clock boundaries and wrapping, and a food event that
advances the original RNG. This compares canonical arena inputs; it adds no
physical keyboard/mouse, host geometry or original-CPU claim.
