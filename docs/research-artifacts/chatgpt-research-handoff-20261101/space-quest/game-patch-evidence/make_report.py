from pathlib import Path
import json,hashlib,platform,sys
R=Path(__file__).resolve().parent
results=R/'results'
b=json.loads((results/'benchmarks.json').read_text());c=json.loads((results/'c_validation.json').read_text());summary=json.loads((results/'comparison_summary.json').read_text())
timing='\n'.join(f'| {label} | {b["timings"][key]["median"]:.4f} ms |' for key,label in [('bytewise','Byte differences'),('asm_instruction_compare','Ordered instruction decode / normalization / comparison'),('asm_symbolic_effect_compare','Bounded ASM effect-summary comparison'),('c_lift_parse_ast_compare','Lift C, parse its AST, compare trees')])
doc=f'''# Game-patch differential study: bytes, SCI assembly and bounded C

Status: **executed private experiment and implementation requirements**.
The prepared repository increment contains documentation only. It does not add a production diff
engine, a general SCI/C decompiler, or a security execution environment.

## Two separate evidence tracks

**Supplied GOG updater.** Re-extraction verified all 36 complete compressed
replacement payloads against their embedded checksums and against the supplied
new full installer. The 36 targets total 5,845,403 expanded bytes: 33 VGA paths and
three GOG metadata paths. The new target copies are byte-identical. The metadata
also declares launch/configuration actions, including INI overwrite and save-path
setup. These are inspected declarations, not an executed Windows installation.
The compiled installer wrapper's complete PascalScript/PE control flow was not
recovered. Payload identity is not a complete installer-side-effect proof.

The old package 20261 remains unavailable. No historical native old/new comparison
was performed. In particular, equal patch-target and full-installer files are an
**output-consistency control**, not evidence that an old game function was fixed.
The updater cannot recreate predecessors from its complete replacement payloads.

**Same game's actual logic patches.** To test nontrivial code changes without
inventing a predecessor, the experiment separately applies five published
ScummVM SQ1 VGA compatibility patch recipes to matching scripts extracted from
the user's new installer. Every signature matched exactly once inside a script
code block. This produces five before/derived-after pairs over four distinct
scripts. The after files are private experimental products of those recipes,
not downloaded historical GOG files. These runtime patches must not be
represented as the contents or effects of the uploaded GOG updater, or as a
verified inventory of its bundled ScummVM executable.

No original DOS game, Windows installer or ScummVM guest session was executed.
The compiled C verifier described below is an isolated model test.

## Patch as the transform oracle

For each selected case, retain:

1. The source container/resource identity and extraction profile.
2. The actual patch's script, signature, match count, selector dependencies and
   write operations. Preserve unchanged bytes written by a patch as writes;
   they are not the same set as bytes whose values actually differ.
3. The matched source offset, checked source bytes, and resulting resource hash.
4. Exact agreement between the supplied candidate result and application of the
   declared recipe; reject a mismatch inside or outside the intended write set.
5. The inferred semantic difference and its assumptions, separately from the
   patch author's explanatory comments and from observed runtime behavior.

The patch is authoritative about its declared transformation. Its comments and
successful application alone do not establish that the intended gameplay fix is
correct or complete. Missing predecessor bytes stay missing, not guessed.

## What the five real patches show

| Case | Changed bytes | Supported difference |
| --- | ---: | --- |
| Timepod animation | 1 | A message-construction argument changes 10 to 9. The eventual send lies outside this selected slice. |
| Force-field generator | 3 | A conditional edge to out-of-resource offset 0xf000 becomes zero-displacement continuation. |
| ID-card counter | 17 | Preserve the incremented numeric counter across a class-reference load, then compare that counter rather than the object reference. |
| Bar animation detail test | 1 | Signed predicate changes from <= 2 to > 2. |
| Orat sound bookkeeping | 4 | The selected read/write pair moves from local slot 7 to self property byte offset 0x1a. The intervening code is retained but opaque to this bounded effect comparison. |

The ID-card pair has **the same multiset of instructions and operands**. Its
order and stack dataflow differ. An unordered fingerprint therefore produces a
false equality on an actual game patch, not just an authored counterexample.
The ordered instruction comparison and bounded effect comparison detect it.

For the old ID-card block, object-versus-integer relational semantics remain
unresolved. The model does not invent an object address or turn it into an
ordinary counter. A confirmed counter write is retained even though the later
comparison is unresolved.

## What the three approaches actually are

- **Bytewise:** exact offset/value changes on equal-size before/after slices,
  plus full-resource preservation and patch-output checks.
- **ASM-aware:** decode SCI1 VM instructions, retain immediates, widths,
  storage identity and branch targets, and compare ordered instructions. A second
  layer symbolically follows the bounded stack/accumulator/property operations
  and compares explicit effects. Ordered token comparison alone is not semantic
  equivalence.
- **C-level:** lift the same bounded operations to C with saved read values,
  explicit 16-bit conversion, typed/opaque object references and ordered effects;
  parse coordinate-free C ASTs and compare them. The C lane shares the decoder
  and semantic assumptions with the ASM lane. It is another representation, not
  an independent source oracle or a general decompiler comparison.

Unsupported instructions stop the lift. Uninterpreted gaps and external effects
are not deleted. Names from selector vocabulary and upstream explanations stay
distinct from the recovered storage/address relationships. The native x86
interpreter is not substituted for the guest scripts that contain these changes.

### C generation failure found and corrected

The first C rendering substituted a getter expression into both a store and a
later comparison. That could re-read the already-updated counter and effectively
increment it twice for the comparison. With an initial counter of 1, the intended
comparison sees 2, while this faulty rendering sees 3. Inspection caught it;
read values are now captured once before the write. A regression check requires
one getter evaluation before the store, and the compiled tests cover this input.

Consequently, readable C is not automatically faithful C. Read timing, aliasing,
operation order, integer behavior and reference types all matter.

## Matched machine timings

All lanes compare the **same six selected spans, 53 bytes per side**, containing
30 instructions per side. This is a small effect-slice experiment, not a
whole-resource/native-function matcher. One patch has two disconnected spans.

Warm in-process medians, milliseconds per complete six-span corpus:

| Work | Median |
| --- | ---: |
{timing}

Twenty-one batches of 30 corpus iterations per lane used deterministically
shuffled lane order. Decode/lift and C parsing costs are included in their lanes;
Python imports and initial parser construction, extraction, discovery, patch
recipe authoring, semantic inspection and verification are excluded. These paths
produce different amounts of explanation. The result does not measure human or
agent comprehension speed, Ghidra/IDA/BinDiff performance, or a general advantage
of C versus ASM. Raw samples and implementation identities remain in the private
reproduction package.

## Validation performed

- All 36 GOG target payloads match the supplied full installer again.
- Two differently structured SCI1 LZW decoders agree on 147 script/vocabulary
  resources. They use the same documented format assumptions; agreement is not
  an independent proof of the format itself.
- Five uniquely matched signatures lie within code blocks. All bytes outside
  the declared write sets are preserved.
- Eighteen base controls and eleven additional controls cover changed signatures,
  duplicate matches, wrong candidate outputs, unchanged inputs, unsupported
  decoding, presentation-address normalization and saved-read ordering. Rebased
  display addresses are not a real recompiled/relocated executable test.
- GCC-compiled generated C agrees with a separately implemented bounded bytecode
  interpreter on **{c['model_comparisons']:,} comparisons**: twelve before/after
  blocks, each over 65,536 selected numeric inputs. Ten additional cases exercise
  the equal-input generator edge. Other state is controlled, not universally
  quantified. **65,536 old object/numeric comparisons remain unresolved** as
  required; agreement on this classification is not a resolved branch result.
- Selected independent literal expectations check the detail predicate, counter
  wrap, continuation target and changed animation argument. Full methods,
  arbitrary callees, all reachable states, timing, display and saves are outside
  the model boundary. The two execution models share explicit property-call
  summaries, so this is not independent original-interpreter parity.

The verifier compiler was `{c['compiler']}`. One final build took
{c['compile_ms']:.2f} ms and execution took {c['execution_ms']:.2f} ms; these single-run
measurements are not included in the lane comparison. Python was
`{platform.python_version()}`. The SCI probe is standalone research code, not a
shipped fDisBull processor module. No new full project pytest or native-game
acceptance result is claimed.

## Source provenance and its limit

The timepod, generator and ID-card definitions were checked against
[ScummVM v2.2.0 script patches](https://github.com/scummvm/scummvm/blob/v2.2.0/engines/sci/engine/script_patches.cpp),
Git blob `c161c0d6a66f719efd4b9555908d5bb57b2ae8d3`.
The bar and Orat definitions were read from the retrieved
[upstream master source](https://raw.githubusercontent.com/scummvm/scummvm/master/engines/sci/engine/script_patches.cpp).
Their retained normalized recipes are reproducible, but the retrieved excerpts
were not independently bound to an immutable upstream commit. Do not advertise
those two provenance chains as fully pinned source recovery.

The operation/reference assumptions and resource decompression rules were
checked against [vm.cpp](https://github.com/scummvm/scummvm/blob/d187209bb0560cbdc8d6adea60cfa3c754a35544/engines/sci/engine/vm.cpp)
and [decompressor.cpp](https://github.com/scummvm/scummvm/blob/d187209bb0560cbdc8d6adea60cfa3c754a35544/engines/sci/resource/decompressor.cpp)
at the stated commit. This mixed-source research profile is explicit; it is not
proof of the exact ScummVM build shipped by GOG or Sierra's DOS interpreter.

## Requirements for fDisBull

1. Add a three-input comparison contract: exact before artifact, patch artifact
   or recipe, and candidate after artifact. Report missing sides and mismatched
   applicability before invoking a semantic comparison.
2. Separate container/installer changes, added files, data/resource changes,
   native code and guest-bytecode changes. Do not force every file into ASM/C.
3. Use byte comparison and patch write maps to select bounded analysis regions.
   Preserve all original bytes and both source identities.
4. Keep an ordered control/dataflow representation with typed storage identities.
   Unordered instruction similarity is matching evidence, never equivalence.
5. Treat C as a derived view with source spans, saved reads, fixed-width behavior,
   explicit object references and unsupported operations. Compare effects as well
   as syntax; retain confirmed writes before an unresolved operation.
6. Require complete input-slice dependencies or explicit entry assumptions. Emit
   enough information for another evaluator to reproduce the claim's boundary.
7. Relate changed source regions to affected UDL/UIL facts, Z actions, HUD fields
   and harness bindings. Reuse unaffected qualification; invalidate dependents
   rather than silently copying old proofs to similar-looking code.
8. Reuse patch recipes as regression fixtures with wrong-source, ambiguous-match,
   unexpected-write, unknown-opcode and changed-order cases. Label synthetic
   controls separately from real game inputs.
9. Measure extraction/discovery, matching, semantics, C presentation and validation
   separately. Selectively generate C where it helps explain or resolve a change,
   rather than decompiling an entire interpreter for an asset-only update.

This is a bounded game-patch test. It neither establishes a security fix in
Space Quest nor upgrades fDisBull's hostile-code safety guarantees. The prepared public PR addition contains this sanitized report only; game files, raw extracted scripts, generated
byte-retaining models, private paths and installation data remain outside Git.
'''
(R/'GAME_PATCH_DIFFERENTIAL_STUDY.md').write_text(doc)
# A small documented regression witness, actually evaluated.
n=1;after=(n+1)&65535;reg=dict(initial_counter=n,stored_counter=after,correct_saved_read_comparison=(after<3),incorrect_reloaded_comparison=(((after+1)&65535)<3),description='Rendering defect in the experimental lifter, not a game defect.')
(results/'c_saved_read_regression.json').write_text(json.dumps(reg,indent=2)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in R.glob('*.py')}
manifest['report']=hashlib.sha256(doc.encode()).hexdigest()
(results/'implementation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('report words',len(doc.split()),'lines',len(doc.splitlines()))
