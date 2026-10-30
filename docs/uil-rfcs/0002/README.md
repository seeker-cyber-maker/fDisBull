# RFC 0002: evidence and literal vectors

This companion supports the [executable Rosetta principles](../0002-executable-rosetta-contracts.md).
It separates executed prototype evidence from proposed production requirements.
It adds no runtime implementation or new UIL encoding.

## Inspected inputs and fresh replays

Two previously delivered, authored experiments were available for inspection:
`UDL_UIL_UDC_Patch_Lab.zip` and `Polyglot_U8_Handoff.zip`. Their identities,
source hashes, tools, exact outputs and bounded result counts are recorded in
[replay-summary.json](replay-summary.json). Both archives passed ZIP integrity.
Both runners were executed again in fresh processes on 30 October 2026 using
unmodified source. Declared semantic results matched their prior receipts.
These are local prototype reruns, not tests of a new fDisBull implementation.

The source archives remain separate user deliveries; they are not included in
this PR. The public receipt is auditable documentation, not by itself a public
reproduction package. Hashes identify inputs and results; they do not prove
semantic correctness. No commercial game content or executable module is added.

### Executable UDL and two UDC targets

The patch fixture authors native x86-64 assembly and its source mappings. UDL
execution calls actual compiled backings, the shared UIL is evaluated by the
unmodified fDisBull 0.22.0 wheel, the original-backed UDC selects retained code,
and one JavaScript UDC generates both program revisions for Node execution.
The UDL/UIL role change changes metadata, not operation syntax or meaning.

Fresh replay passed:

- Exact reconstruction of both 512-byte reference code images and exact patch application.
- 4,096 full input-state cases across the original, executable UDL, shared evaluator, native UDC and JavaScript paths, against a separate arithmetic oracle.
- 6,656 per-block comparisons and 16 negative/sensitivity controls.
- Six unchanged backing slots; only decision/equality definitions change, totaling 27 differing byte positions.
- A changed equality result is rejected by the fixed native definitions but genuinely emitted by the generic JavaScript compiler; it is not equivalent to the reference post-patch result.

The test exhausts all 256 control inputs in eight selected counter contexts,
not every combination of all state. Exact byte equality concerns the code image,
not ELF loader metadata or complete process state. Scratch registers, flags,
cycles and external effects are outside the declared semantic observation.
Native layout reserves space for the added handler; arbitrary relocation and
new native code generation are not demonstrated. Mappings are authored, not
inferred automatically from an unknown game. Pre and post intentionally differ.

### C to JavaScript to C

The second runner compiles a Node-API C addon and loads it into the same Node
process. Native C computes a byte, JavaScript adds through a private Uint8Array,
and native C consumes the exported byte. This is real native/JS execution,
not a Python simulation and not a generic UDC implementation.

Fresh replay passed all 65,536 ordered pairs of byte inputs, 52 invalid-input or
arity checks, and a control detecting omitted wrapping. The output digest is
identical to the prior receipt. The scalar carrier is JavaScript Number; no
scalar eight-bit JS storage is claimed. The vector remains private to synchronous
JavaScript. Rust, shared-memory layouts, ownership transfer, concurrency,
hostile-code isolation and performance advantage were not tested.

## Design fixtures and prospective gates

[vectors.json](vectors.json) records explicit value correspondences, three
handler-boundary examples, a compiler-sensitivity edit and byte-handoff examples.
It is an authored design fixture, not a newly registered shared-IL format.
The Roman codec is deliberately defined only for III and IV; it does not claim
a general Roman-numeral parser or that formatting is itself semantic recovery.

The full R01-R18 table in the RFC specifies future acceptance. Literal arithmetic
and document checks must not be counted as executing those production features.
The source experiments substantiate portions of R02-R05 and R09; they do not
fully qualify all domains or all composition mechanisms in those rows.

## Reproduction with the separate authored deliveries

On a compatible Linux x86-64 host, unpack the two source archives into private
working directories. Requirements are GCC/binutils, Node with Node-API headers,
and a separately supplied compatible fDisBull evaluator wheel. Inspect scripts
before running; these are trusted authored native-code fixtures, not a sandbox.

```sh
python udl_patch_lab/run_lab.py \
  --fdisbull-wheel /path/to/fdisbull-0.22.0-py3-none-any.whl \
  --output /path/to/new-private-output
python polyglot_u8_lab/run.py
```

The latter runner writes only inside its extracted fixture directory. Match
source/archive identities to the receipt first. Tool or host differences require
a new receipt; do not assume identical native module hashes across toolchains.
No whole-repository test suite or new native-game investigation was run for this
principles-only change.
