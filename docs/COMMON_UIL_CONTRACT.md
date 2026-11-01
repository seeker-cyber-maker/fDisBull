# Common indexed UIL contract

This implements the first bounded common contract, `fdisbull-common-uil-1`.
It composes source-independent typed functions and selected block definitions,
with separate orchestration and presentation. It is additive: existing scalar,
memory, AGI, Zork and console format identifiers retain their own meanings.
The new adapter recognizes only the admitted source profiles below.

The implementation is in `common_uil.py`, `uil_catalog.py`, `uil_runtime.py`,
`uil_codegen.py` and `uil_store.py`. The
[conformance study](COMMON_UIL_CONFORMANCE.md) assembles a new program from
mixed-source blocks, checks food arithmetic, and imports Snake-shaped and
full private Snake models. Source correspondence, model equivalence, emitted
code, original CPU execution and host interaction remain separate gates.

## The three documents

| Document | Responsibility |
| --- | --- |
| UIL | Typed zero-based variable/constant tables, indexed functions/imports, expressions, ordered control and effect requests. No source variable names, native addresses, resource paths, literal values or target ABI are embedded in these tables. |
| Orchestration | Select each exact implementation; identify the call target; generate typed argument/result shims; declare frame ownership, call-depth and optional context epochs. |
| Presentation | Bind each constant value and initial variable value, resource text/locators and optional display names. The current target storage profile is `indexed-owned-frames-1`. |

For this contract, presentation means concrete program/data realization rather
than UI decoration. A string or sound has a resource-table index in UIL and a
concrete value in presentation. Python/JavaScript own the actual object and
array locations; UIL has no arbitrary host-memory-write authority. A future
native pointer/layout ABI needs a separately admitted layout profile. Supplying
an unsupported memory layout is refused rather than ignored.

Function identity has two levels. Local functions use indices in the program's
function table. Imported reusable functions use a content-addressed semantic
definition in the catalog, then an exact implementation selection. Generated
symbol names and physical argument/result variable slots belong to the output
and its shim manifest. No source binary's historical function name is required.

## Program schema

The exact top-level fields are:

```json
{
  "format": "fdisbull-common-uil-1",
  "capabilities": ["core.scalar@1"],
  "imports": [],
  "functions": [{
    "variables": [{"type": "u16"}],
    "constants": [{"type": "u16"}],
    "inputs": [0],
    "outputs": [0],
    "max_steps": 20,
    "body": [{
      "op": "set", "dst": 0,
      "value": {"op": "add", "type": "u16", "args": [{"var": 0}, {"const": 0}]}
    }]
  }],
  "entry": 0
}
```

Constant slot zero's value is supplied by presentation. Binding it to `"1"`
produces a wrapping increment; binding it to `"2"` changes the realization.
The program digest alone therefore does not identify executed behavior. The
complete closure binds presentation, catalog, orchestration and generator too.

Every function has its own frame and tables. `inputs` and `outputs` identify
variables in that frame. References are integers, starting at zero; booleans,
negative indices, duplicate ports, implicit literals and unknown fields refuse.

Types are `bool`, signed/unsigned 8/16/32/64-bit integers, `text`, `resource`,
and fixed `u8-array`, `u16-array`, `u32-array` descriptors with `length`.
An array has at most 131,072 cells; total declared array storage per function
is at most 262,144 cells so an input arena and independent result arena can
coexist. Aggregate call depth is at most 32. Arrays are value-owned; an output
must not silently alias a caller input.

The capabilities are `core.scalar@1`, `core.array@1`, `core.calls@1` and
`host.effects@1`. Required capabilities are checked across all local functions,
unselected branches, imported signatures and selected implementations. Unknown
capabilities are unsupported. The program is not reduced to only a witnessed
execution path during validation.

## Numerical and control behavior

References are `{"var":0}` and `{"const":0}`. Expressions use explicit types
and `args`; `load` instead names an array slot and unsigned index expression.
Supported operations are add/subtract/multiply, divide/remainder, bitwise
and/or/xor, shifts, comparisons, boolean not, explicit cast, select and low-byte
even parity. All operands are evaluated eagerly, including both select arms.

Integer arithmetic wraps at its declared width. Signed division truncates
toward zero; remainder satisfies `a = quotient*b + remainder`. Division by
zero, invalid shift counts and out-of-bounds memory refuse. Explicit casts
perform width wrapping or boolean nonzero conversion. Numeric operators do not
silently mix widths or signedness. Resources/text cannot participate in integer
arithmetic. A legacy masking or checked narrowing operation is made explicit
by its importer rather than changing common-core semantics.

Statements are set, indexed store, if, bounded while, require, return, local
call, imported invoke, effect request and transparent group. Calls identify a
function/import index, argument expressions and destination variable indices.
The local call graph must be acyclic. Catalog implementations are closed
functions: their own unresolved call/invoke dependencies must first be composed
explicitly through orchestration.

An executed non-group statement costs one step, including while entry. Every
while-condition evaluation costs another step, including the final false test.
Expressions have structural budgets but no step charge. Child work charges
all active caller frames and the aggregate budget. Transparent grouping adds no
charge. A function and aggregate execution admit at most four million steps.
These are model budgets, not native CPU cycles or timing-equivalence claims.

## Presentation bindings and exact encoding

`fdisbull-uil-presentation-1` requires `program_sha256`, one function binding
per function, and a resource table. Each function binding has `constants` and
`initial`, in exactly the corresponding slot order. Integer scalar values use
canonical decimal strings (`"0"`, `"-32768"`); booleans stay booleans, resource
indices stay bounded integers, and arrays contain typed integer cells. There
are no implicit defaults for local-program slots.

Resources are `{kind:text,text:...}` or a graphic/sound/music kind plus `uri`.
The URI is data; neither the interpreter nor generated programs open it.
Presentation optionally carries a `names` debug map and
`layout:{profile:"indexed-owned-frames-1",description:...}`. Other layouts
refuse. Native source addresses, segment selectors and backing offsets remain
source/adapter evidence, not generic UIL variables.

Canonical documents use UTF-8, sorted object keys, compact separators and no
implicit Unicode normalization. Semantic floats and duplicate input-file JSON
keys are rejected. Document hashing identifies a concrete representation, not
a mathematical-equivalence class. The Python runtime uses exact integers;
generated JavaScript uses BigInt internally and decimal strings for integers
outside JSON's safe-number range. Input values are validated before narrowing.

## Catalog and single-instruction fallback

`uil-catalog` accepts a list of UDL descriptors. Current adapters are:

- `scalar-il`: a pure `fdisbull-il-1` program plus explicit input/output names.
- `memory-uil`: an admitted `fdisbull-memory-uil-1` program and function name.
- `c-u16`: the existing restricted uint16 register statement reader.
- `python-u16`: parsed masked uint16 assignments; no eval/exec or arbitrary
  Python execution. Unmasked `ax += 1` is not a wrapping-u16 definition.
- `x86-16`: actual bytes for exactly one decoded register `INC`, `ADD` or `ADC`;
  explicit `bits` also admits decoder modes 32/64 and 8/16/32/64-bit register
  operands. Other instructions, prefixes, memory operands and incomplete decodes
  refuse. The input selector name is historical; metadata records actual mode.
- A supplied common function, constants and origin-language label. An arbitrary
  label records an authored source-correspondence declaration; it is not a
  general compiler or proof for that language.

Instruction fallback uses Capstone's actual complete decode and operand facts.
By default it exposes the destination plus CF/PF/AF/ZF/SF/OF. INC preserves
incoming carry. ADC consumes carry even when flag outputs are explicitly
projected away. Register views are isolated typed ports: whole-register aliases,
memory, traps, ABI, timing and OS/device services are outside this profile.
This is a working bounded instruction fallback, not arbitrary DOS-to-ARM64
conversion. Unsupported code remains unsupported; it is never a successful
no-op or a claim that x86 bytes run on another ISA.

The catalog normalizes port-first variable numbering, referenced constants,
duplicate typed constants and transparent grouping. It preserves charged
statement order, execution budgets and outputs. Projected INC, restricted C
increment and masked Python increment therefore share one `semantic:<sha256>`
identifier. A change from add-one to add-two produces another identifier.
Copy elimination, algebraic rewriting, arbitrary temporary inlining and
automatic cross-language equivalence proving are not implemented.

Each realization retains a separate `implementation:<sha256>` identity,
language, source hash, source-map/evidence metadata and assurance. Raw input
source is not copied into catalog metadata. Unknown source descriptors remain
in bounded `rejected` diagnostics; compilation requires every requested import
to have a valid exact selection. Group and implementation hashes are rechecked
on load and use. Matching IDs establish normalized-model identity, not original
source fidelity. An RNG/rule variant cannot masquerade as an equivalent backing.

## Recoverable higher-level views

`uil-fold` wraps a function's complete body in a transparent group and returns
an immutable recovery document binding before/after digests, the function index
and exact original child graph. `uil-expand` checks those bindings and restores
the original program exactly. A changed folded program or corrupted recovery
refuses. Nested fold views retain earlier graphs.

The supplied group `semantic_id` is an authored label, not execution authority.
Catalog matching recomputes normalized child semantics and does not trust that
label. Grouping alone recovers no new intent and selects no hidden backing.
Reusable, executable higher-level blocks enter the verified catalog and are
called explicitly through indexed imports. This distinction preserves a useful
view without allowing a misleading label to change computation.

This initial seam handles explicit function/capsule boundaries. It does not
automatically cut arbitrary native control flow, establish unknown liveness,
remove overlapping instruction interpretations, or infer an entire game rule.
Original files remain retained by their private project/source backings.

## Orchestration, shims and effects

`fdisbull-uil-orchestration-1` binds the program digest, exact import-to-
implementation choices, `copy-in-copy-out` ownership and a call-depth limit.
The generated shim manifest maps logical port ordinal to concrete callee
variable slot, type and ownership. Arguments and results are copied across
independent frames. Calls report the implementation actually entered, including
origin language and completion/refusal; matching final output alone is not used
as evidence that a selected block ran.

Optional context epochs identify session, generation, state revision, selection
epoch and provider epoch. `prepare_execution` owns the plan and context before
computation. `finish_execution` consumes its ticket once and rejects stale or
ill-typed context. It is a pure-result guard, not a GPU scheduler or a lock on an
external application: a host must serialize its actual check-and-commit. No
provider buffers or physical work are allocated by this profile.

Invocation diagnostics are bounded. Arrays over 64 cells and UTF-8 text over
256 bytes are retained as length/size plus SHA-256, while real argument/result
values still cross the shims unchanged. The profile allows at most 1,024 call
records, 65,536 trace cells, 256 effect events and one MiB of event JSON. Budget
exhaustion refuses atomically before retaining unbounded diagnostics. These
limits participate in the emitted realization manifest.

The current services are `text.show(resource)`, `image.show(resource)`,
`sound.play(resource)`, `music.start(resource,looping)` and
`music.stop(resource)`. All return ordered **plans**. Statically known resource
indices/kinds are preflighted across selected implementations; dynamic resource
inputs are checked when used. With effects, the result is `pending_host`, with
original committed state and separate proposed state. A later model failure
discards staged events because none has run. Executing effects, audio handles,
completion callbacks and partial physical-effect recovery need a host capability
with its own qualification. There is no automatic retry or backend fallback.

## Standalone output and persistence

`uil-compile` emits actual Python or JavaScript functions, branches, loops,
typed helper operations and call shims. It does not embed a UIL AST interpreter,
import fDisBull at runtime or execute source C/x86 through a foreign ABI. Source
languages enter through their admitted UDL models; output backends realize the
selected common definition. This is semantic reuse rather than byte-identical
polyglot linking.

The output directory must be new and outside Git. The manifest binds the full
program/presentation/catalog/orchestration closure, target, generator hash,
limits, selected source metadata, shims and emitted source hashes. Emission is
reported separately from execution. Run `program.py` or `program.mjs` with JSON
lines such as `{"inputs":[65535]}`. Each request gets a fresh owned invocation.

Project methods `store_uil_package`, `uil_package_info` and `uil_packages` retain
immutable packages under `uil:<sha256>`, with current-parent checks and a source
version identity. Reopen verifies canonical document bytes, hashes, references
and source-version identity. It does not promote source declarations to proof.
Updating or patching the source does not rewrite earlier packages or silently
retarget their bindings. New storage is lazy and uses savepoints; failed stores
do not commit an enclosing caller transaction.

## Agent and CLI use

The following JSON methods and corresponding CLI commands are discoverable:
`uil-check`, `uil-catalog`, `uil-run`, `uil-compile`, `uil-fold`, `uil-expand`,
`uil-store`, `uil-info`, `uil-list`. Documents can be provided directly through
JSON methods or explicitly named files. For example:

```sh
fdisbull uil-catalog /private/blocks.json
fdisbull uil-check /private/package.json
fdisbull uil-run /private/program.json --presentation /private/presentation.json \
  --catalog /private/catalog.json --orchestration /private/orchestration.json \
  --inputs /private/inputs.json
fdisbull uil-compile /private/program.json --presentation /private/presentation.json \
  --catalog /private/catalog.json --orchestration /private/orchestration.json \
  --target javascript --output /private/new-output
fdisbull uil-store /private/analysis.fdb synthetic /private/package.json
fdisbull uil-info /private/analysis.fdb uil:RECORDED_DIGEST --full
```

Full packages/realizations may contain game-derived semantic data, resource
locators or initial state. Keep them private unless separately reviewed. This
feature changes no publication policy, installed release, VM or original file.
