# Recovered compiler and analysis adapters

These source contributions are adapted to the 0.35 integration interfaces.
This page records delivered seams and their limits, not native platform or
release acceptance. The release owner still qualifies the final combined SHA.

| Recovered source | Integrated capability | Boundary |
| --- | --- | --- |
| `02eb26f42381e884b423b1a1fd65bde9ac0c6894` | Closed scalar IL-v1 LLVM emitter | Authored unsigned-byte scalar subset; no TCG or arbitrary binary lift. |
| `0dc3790f5f71ff5128c857e0c38b816657ec1d5e`, `b6051fe212c9e17a490e9955e97ed657b0518a78` | Standard DOS COM/MZ compiler, fixed data/relocation layout, pinned implementations and Z-machine v3 scaffolds | Exact source identity and explicit assumptions; terminal MZ returns require a process-return adapter. Stories and original source bytes remain private. |
| `0eaf75d1a30d70fcf6d0649be8e78a80178d6cd1`, `1f8d2636d1d8a561bddaf322c7770a9e3d78fe27`, `6b44cb063bc454de1ff69b1b0a9e54628d287c7b`, `9a16c5ecbc68ad39853f2ff76e5d48ed4977bced`, `cb976470f73149342108f4125e70e0bb332d6a84` | Civ source examples, city/game semantic scenes, source decoders, production/buy models, game variants; integer `ge`, wrapping multiplication and truncating division in tree IL and generators | Source-backed and authored models retain their target/edition limits. Originals, screenshots, state-byte receipts and the byte-retaining atlas are excluded. Exact original-byte checks require explicit private inputs. |
| `f4f9e3392da6a92a7e8dcd3277a86aa626694d9f` | Indexed UIL-record validator/interpreter | Integer operands are checked explicitly; this does not replace the common UIL contract or imply universal interchange. Its integer-admission fix is retained over the older dirty snapshot. |
| `3e437a9e9ca313a2a24d18ef928a40fc5084b5f7` | CHIP-8 Python UDC example/compiler | Guarded partial evaluation and fallback against the pilot VM. Supplied Snek example is CC0-derived; a caller supplies its pinned ROM. No historical COSMAC parity claim. |
| `3e5900ee916578c6b2ab3be0654930816a46e9ff` | SNES actor, conversation, keyword, menu, opening, transition and explicit hardware-input components | ROM and runtime state stay caller-owned and private. Host source generation and interpreted model checks do not establish native game equivalence. |
| `9df57f8f62f0374e7f0b527c4eeb40152d12fd79` | Bit-influence pilot and CMP/JAE negative control | Hand-modeled, path-local observer; not a native replacement or complete FLAGS/interrupt proof. |
| `fcef2877320e0981d5b979ad9bba1e1d1dcbd488` | Optional Ghidra, Reko and DCC ASM-to-C views and public engine contract | Tools are caller-selected; diagnostic C stays unverified unless the bounded independent scalar equivalence gate passes. No automatic tool download/install. |
| `3136d2faa369ac499043dc560093555be4b62b6c` | Authored shared Colonization production helpers | Source/UIL comparison is bounded; physical addresses belong to separate source bindings. |

The port preserves current IL-v2/control-flow/table support, signed-byte and
signed-result ABI behavior, SYS and ARM64 source identity, and current provider
and storage policy. Generic code backing export remains independent of the
flat-only compiler profiles. DOS compiler admission is explicitly COM/x86-16;
this contribution does not claim a mixed-mode LE compiler.

The DOS and Z-machine entrypoints appear in `fdisbull methods` and command help.
Other bounded prototypes retain their documented Python/example interfaces.
Source-checkout examples stay out of tool-only distributions. Their tests skip
explicitly when the corresponding example is not packaged, rather than
attempting to obtain commercial inputs or invoking a runtime implicitly.

Focused integration verification and exact source identities are recorded in
the contribution handoff. Historical target/runtime reports retain their own
frozen identities; they do not qualify the current release by inheritance.

The existing `asm_to_c(lift)` call retains its v1 builtin result. Selecting
`engine="builtin"`, `"ghidra"`, `"reko"` or `"dcc"` explicitly opts into the
new interchangeable v2 view and its optional equivalence check.
