# Executable UDL -> UIL -> UDC: split one handler into two

## Result

The requested experiment ran successfully on an authored native x86-64 fixture.
Both pre- and post-patch executable UDL representations project into the existing
`fdisbull-il-1` UIL syntax. An original-backed UDC reconstructs each reference
code image exactly. A different, shared JavaScript UDC definition generates two
standalone programs from those same UIL documents. The JavaScript programs do
not call native code, load the original binaries, or require fDisBull at runtime.

This is an executed, bounded demonstration of the architecture, not a proposed
pipeline and not automatic recovery of an unknown game. Source-to-UDL mappings
were authored for the fixture and then checked against its native backings.

## The fixture

State contains six fields: unsigned 8-bit `x`, `number` and `outcome`, and unsigned
16-bit `before`, `after` and `calls`. Each occupies a separate 32-bit ABI storage
cell, with explicit arithmetic width in both the code and representation.

The program executes:

1. Unrelated prefix: increment `before` by 7, modulo 65536.
2. Calculate `number = (3*x + 7) modulo 256`.
3. Select a result handler against unsigned threshold 128.
4. Unrelated suffix: increment `after` by 11, modulo 65536.

Each result handler sets an observable outcome code and increments `calls` once.
The pre-patch program has two handlers: lower -> 10; higher-or-equal -> 20.
The post-patch program has three: lower -> 10; equal -> 30; higher -> 20.
The existing outcome-20 implementation is reused without modification; only its
calling condition narrows from higher-or-equal to strictly higher.

The native fixture deliberately reserves eight 64-byte slots, for a 512-byte
code image. The equality handler occupies previously unused padding. This
isolates the requested experiment from relocation and arbitrary code growth.
The generated ELF shared-library loaders are test adapters, not the boundary of
the byte-for-byte reconstruction claim.

## The executable route, including UDL

```
pre reference ASM  -> executable UDL + backing bindings -> UIL pre
                                                        |-- native UDC pre -> identical pre code
                                                        `-- JavaScript UDC -> standalone pre JS

actual guarded patch layer

post reference ASM -> executable UDL + backing bindings -> UIL post
                                                        |-- native UDC post -> identical post code
                                                        `-- same JS UDC    -> standalone post JS
```

UDL and UIL use the same block syntax, types and node identities. The existing
`change_role` operation changes only the role metadata. Executable native backing
bindings live in separate manifests; native offsets do not appear in the UIL.
The block structure is therefore shared, while execution authority is explicit.

The **executable UDL path invokes the real native backings** for the prefix,
calculation, decision and suffix. It does not simulate those operations through
the Python IL evaluator. Before invocation, it checks the UDL document identity,
semantic keys, source image identity and each backing's bytes. Editing the UDL
without rebinding rejects execution rather than silently running obsolete code.

The **UIL path** uses the unmodified `execute_il` evaluator from the retained
fDisBull 0.22.0 wheel. Its syntax has no general less-than operator. For this
bounded u8 domain, `not bit_test(number, 7)` expresses exactly `number < 128`.
The post-patch branch then checks equality with 128 using the existing `eq` node.
No production opcode or role was added.

The **native UDC profiles are derived from the executable UDL backings**. Typed
structural keys select the implementation for each unit. The native UDC neither
receives a desired pre/post version flag nor consults the reference output hash
when selecting definitions. The known reference is used afterward for validation.
Unsupported semantic edits have no matching implementation and are rejected.

The **JavaScript UDC** walks either UIL tree using one template definition for
set, modular add/subtract and conditions. It has no pre/post special case and no
handwritten replacement version of either complete program.

## What changed at each representation

| Representation | Patch-related change |
| --- | --- |
| Native source | Add an equality branch and its handler; keep original handlers and surrounding code |
| Guarded byte layer | Two 64-byte replacement spans, with exact original/target identities; 27 byte positions differ |
| Executable UDL | Revise the decision binding; add the equality implementation; reuse unrelated native backings |
| UIL | Retain the lower branch; replace the old else body with `if equal then new handler else existing handler` |
| Native UDC definitions | Exactly two slot definitions differ: decision and equal |
| JavaScript UDC definition | No pre/post change; one definition compiles both UIL versions |
| Generated JavaScript | Only the formerly combined branch gains the equality split |

Exact byte changes are 8 positions in the decision slot and 19 in the new
handler slot. The entry wrapper, prefix, calculation, lower handler, existing
higher handler and suffix remain byte-identical: six reused slots.

An unchanged caller's bytes do not imply unchanged transitive behavior. The
entry wrapper calls the changed decision, so the whole-program result changes
at equality even though the wrapper can be retained. Its old whole-program
qualification cannot simply be inherited across the changed dependency.

The semantic tree delta is also serialized. Applying that delta to pre UIL
produces post UIL exactly. It records the compared authored mappings; it is not
claimed as an automatic inference of meaning from arbitrary patch bytes.

## Observable examples

| Input x | Computed number | Pre outcome | Post outcome |
| ---: | ---: | --- | --- |
| 40 | 127 | Lower, 10 | Lower, 10 |
| 211 | 128 | Higher-or-equal, 20 | Equal, 30 |
| 126 | 129 | Higher-or-equal, 20 | Higher, 20 |

For input x=211 with zeroed counters, both versions finish with `before=7`,
`after=11`, `number=128`, and `calls=1`. Only `outcome` changes, from 20 to 30.
Across all 256 x values, 128 select the lower handler. The old remaining 128
inputs split into one equality input and 127 strictly-higher inputs.

## Tests actually executed

For each revision, all 256 control inputs were tested in eight counter/boundary
contexts: 2,048 full input-state cases per revision, 4,096 in total. Five execution
paths were compared with an independent arithmetic oracle:

- Original native program.
- Executable UDL composition using native backings.
- The real fDisBull UIL evaluator.
- Native UDC reconstruction, linked and executed.
- Generated standalone JavaScript, executed by Node.

All passed. JavaScript's visited-node sequence also matches the UIL evaluator,
including one selected handler and prefix-first/suffix-last execution.

An additional 6,656 per-block cases compare native backings against their IL
slices. These include every 8-bit number at decision entry and counter edge
values, not only numbers obtained through the normal entry wrapper.

Sixteen negative/sensitivity controls passed, including:

- The old native compiler profile rejects the new UIL when the new backings are absent.
- A changed UDL document cannot silently run its obsolete bound native implementation.
- Wrong patch base, wrong expected bytes, incorrect replacement and overlapping edits reject.
- Altered native backing bytes and changed typed interfaces reject.
- Changing the equality result to 31 is rejected by the retained native UDC
  because no such source backing exists.
- The same edit generates JavaScript that actually produces 31. It is correctly
  not equivalent to the reference post-patch program, whose result is 30.
- Reusing the pre-patch branch is exposed by x=211.
- Removing modular arithmetic from the JS compiler definition produces a detected
  counterexample rather than an apparently successful translation.
- Negative, oversized, fractional and boolean inputs are rejected by the checked
  native boundary, UIL evaluator and JS program.

These are compiler/patch controls, not discovered game vulnerabilities. The
experiment illustrates how generated code can be tested for additional invariants
without inventing a new defect in the source program.

## Exact identities

Pre reference 512-byte code image:
`7f278b753606622c96420d6e3a6639a191c38e2c66de7f801bad2d7b0706e982`

Post reference 512-byte code image:
`d05571bc894b61272d1d0cbf99368392fca288c819d64d4ce0290b670d60507d`

Both native UDC results match their complete reference code images, including
unchanged padding. Applying the guarded patch to pre also reproduces post.
The assembler object has no unresolved relocations. No comparison of ELF loader
metadata or entire OS process state is claimed.

Tool observations: Python 3.13.5, GCC 14.2.0, Node v22.16.0, Linux x86-64.
`results/provenance.json` pins the imported wheel and its unmodified evaluator.
The wheel is not redistributed in this delivery.

## Reproduce

On Linux x86-64 with GCC/binutils and Node:

```sh
python run_lab.py --fdisbull-wheel /path/to/fdisbull-0.22.0-py3-none-any.whl --output ./rerun
```

An installed compatible fDisBull package can be used instead of the wheel flag.
The runner verifies the authored assembly, rebuilds the backings and compiler
profiles, regenerates both outputs, and performs the tests. It does not require
game assets, an emulator, network access, or the prior Lost in Time artifacts.

The generated JS is independent of native execution and can be run directly:

```sh
printf '%s\n' '{"$x":211,"$number":0,"$before":0,"$after":0,"$outcome":0,"$calls":0}' \
  | node artifacts/post.generated.js
```

Or import `run` from that file in another Node program.

## Fresh delivery replay

The delivered archive was extracted into a new directory and rerun in a fresh
Python process, using the same retained external evaluator wheel. All checks
passed again. Fifteen reference/reconstructed code images, representation files,
compiler profiles and generated-code artifacts matched byte-for-byte. The receipt
is `results/reproduction.json`. This is fresh-process reproducibility on the same
machine, not qualification of another architecture or host.

## Boundaries

The source mappings and fixed block boundaries are authored for this example.
The native generator is a source-backed selector/assembler for this fixed profile,
not an arbitrary machine-code compiler. JavaScript generation supports only the
implemented pure u8/u16 subset. State equality covers declared memory fields;
CPU scratch registers, flags, cycles, exceptions and external effects are outside
this model. All 256 control inputs were tested, but not the full Cartesian product
of every unrelated state field. This is executable evidence, not a general formal
compiler-correctness theorem.

The prototype uses existing fDisBull shared IL without changing its production
schema or native compiler. Its sidecar adapters are experimental, not a claimed
merged feature. A real game's source recognition and block qualification costs
remain separate from the small conversion timings saved with this experiment.

## Conclusion

The test supports the proposed architecture: preserve executable UDL blocks,
project their common representation into UIL, derive an original-backed UDC,
and validate exact pre/post reconstruction. A target-specific UDC can then
compile the same UIL into independent executable JavaScript.

The patch need not cause another whole-program reconstruction. Changed backings
and their affected semantic dependencies are the unit of work. The source-backed
UDC preserves known implementations; the alternate UDC makes the supported
meaning portable.
