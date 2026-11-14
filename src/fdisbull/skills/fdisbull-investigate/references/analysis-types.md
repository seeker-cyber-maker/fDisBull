# Types, address spaces and candidate accesses

Use when bytes are available but their layout or address interpretation is
uncertain. For executable examples see [next steps](next-steps.md). Reuse the
selected install and inspect a method's help/schema for required arguments.

## Establish the address before interpreting the value

| Identity | How to establish it | Common wrong inference |
| --- | --- | --- |
| File offset | Named file plus bounded byte read | Offset 0x40 automatically means native address 0x40. |
| Static mapped address | `status PROJECT` loader mapping, section or segment identity | Every format uses raw base + offset. |
| Live address | Backend's actual mapped process/guest state and segment/bank context | A static address transfers unchanged through ASLR, relocation or banking. |
| RAM/ROM or file-backed constants | Platform map and the applicable runtime mapping/permissions | A successfully typed ROM table is a live mutable player structure. |

For raw examples only, base + offset gives the static address. DOS segment:offset,
PE virtual addresses, relocation, overlays and console banks require the relevant
mapping. A screenshot, source name or plausible integer does not supply it.

Width selects how many bytes are read; endian selects their order; signedness
selects the numeric interpretation. For `ff ff`, u16 is 65535 and i16 is -1.
A pointer is an encoded address under a declared address-space model, not the
pointed-to object's value. Units and roles require evidence beyond decoding.

## Choose a structural tool by the question

| Question | Surface | What its output does and does not establish |
| --- | --- | --- |
| Which layouts already exist? | `types` | Reuse an applicable definition; names are authored claims. |
| Can I express this layout? | `define-type` | Explicit struct/array/scalar/pointer layout; validate size, offsets and overlap. |
| Interpret a retained native region | `apply-type`, then `typed-data` | Static retained little-endian bytes, not a live process read. |
| Interpret an attached file | `apply-file-type`, then `file-data` | File-relative fields, not a memory mapping. Recipe 2 uses real calls. |
| Find candidate code boundaries | `function-patterns`, `code-regions` | Pattern/region evidence; not function reachability or dynamic execution. `code-regions` requires an MZ project. |
| Find instructions that may access a field | `memory-accesses` | Address matches and unresolved candidates under analysis assumptions; not all runtime writers. |
| Supply a known function signature | `set-function-type` | An explicit assertion; retain origin and ABI instead of treating it as inference. |
| Reuse an exact known body | `add-signature`, `capture-signature`, `signatures` | Retain architecture, bitness, exact bytes and provenance. A name match is not behavior proof. |

Example JSON requests for an **already established** retained native region:

```json
{"method":"define-type","params":{"project":"analysis.fdb","name":"Pair","definition":{"kind":"struct","size":4,"fields":[{"name":"count","offset":0,"type":"u16"},{"name":"flags","offset":2,"type":"u16"}]}}}
{"method":"apply-type","params":{"project":"analysis.fdb","address":"0x2000","type_name":"Pair","name":"candidate_record"}}
{"method":"typed-data","params":{"project":"analysis.fdb","address":"0x2000","max_items":8}}
{"method":"memory-accesses","params":{"project":"analysis.fdb","address":"0x2000","size":4,"access":"write","limit":20}}
```

Send a single JSON object through `fdisbull request '<object>'`, or use the
matching CLI. Replace the example project/address with observed identities.
Address 0x2000 is not a default for real targets. If no such retained region
exists, establish the mapping first; do not import or bind arbitrary bytes just
to make a query pass.

## Read outcomes and choose the next step

- A type applies: compare leaf values and original bytes, then inspect the
  consumer or controlled runtime changes to qualify meaning.
- A binding fails: distinguish unmapped bytes, insufficient size, overlap and
  invalid layout. Fix that prerequisite rather than padding or relabeling data.
- A static access matches: inspect its instruction, width, segment assumptions
  and caller/state. Use a live watch when the claim requires an observed writer.
- No access matches: check analysis coverage and unresolved candidates. Empty
  output is not proof of absence. Paginate `has_more` only if more results matter.
- A branch/call is unresolved: preserve the alternatives; obtain the required
  input, mode or mapping before extending the claim.

Typed names and signatures are useful hypotheses. They never supply their own
independent confirmation. For exhaustive absence or a disputed writer claim,
use [binary claim verification](binary-claim-verification.md); for bounded
reconstruction use [reconstruction](reconstruction.md).
