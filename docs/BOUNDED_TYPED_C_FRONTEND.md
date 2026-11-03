# Bounded typed C to UIL

`fdisbull.console_synthesis.c_frontend.import_c` imports a selected function from
trusted development C through a caller-selected local Clang executable. It reads
Clang's typed AST and produces the existing `fdisbull-il-1` representation. This
is an experimental Python API; it adds no CLI command, Ghidra integration, p-code
importer, or new UIL format.

## Small scalar example

For this source in `bounded_rule.c`:

```c
unsigned char increment(unsigned char x) {
    return (unsigned char)(x + 1);
}
```

Import and execute the admitted function:

```python
from pathlib import Path
from fdisbull.console_synthesis.c_frontend import import_c

function = import_c(
    Path("bounded_rule.c"),
    "increment",
    clang=Path("/absolute/path/to/clang"),
)
assert function.run({"$arg_x": 255}) == {"return": 0}
```

The returned `ImportedFunction` retains its UIL document, input/output ports,
source hash, Clang version, invocation, and typed AST. `state` validates supplied
logical inputs; the emitted document also contains admitted-domain checks, so a
caller cannot bypass those restrictions merely by invoking the shared evaluator.

## Admitted contract

The compiler invocation fixes the source ABI to x86-64 Linux LP64 and C11. Do not
use that choice as evidence for the ABI of a recovered binary. The profile admits
integer scalars, typedefs, explicit conversions, local scalar storage, forward
conditionals and early returns, bounded constant-index local arrays, addition
and subtraction, multiplication by a small constant, and selected constant
masks and shifts on nonnegative admitted inputs. Comparisons retain signedness.
Signed arithmetic requires a domain establishing no overflow; out-of-range
signed conversions refuse. Unsigned conversions preserve modulo behavior.

The optional `bindings` argument can constrain scalar input domains, bind a
constant parameter, or declare fixed input/output buffers. A buffer contract
declares non-null, disjoint `uint32_t` cells and logical labels. Those pointer,
size, alias, and input-domain assumptions come from the caller. They are not
automatically recovered from arbitrary C. Output cells must be definitely
written on every admitted return path, and input-buffer writes refuse.

Loops, unknown calls, globals, volatile or atomic effects, arbitrary pointers,
dynamic indexing, division, floating point, and other unsupported constructs
refuse. The source and AST have explicit size bounds. Source content is checked
for changes during analysis. Transitive header and complete toolchain capture
are not supplied; this API is not a sandbox for hostile preprocessor input.

## Qualification and target limits

This adapter differs from the exact-shape source readers described in
[ROM_SEMANTIC_ROUTE.md](ROM_SEMANTIC_ROUTE.md): it traverses a real typed C AST
within the bounded profile. It does not establish that the input C came from a
decompiler or matches an original machine program. Qualify that source edge
separately when making a recovery claim.

Import success also does not establish that every UDC can compile the resulting
document. Existing console and native targets admit their own subsets. Compiling
the input C as a comparison oracle is separate from emitting a target from the
imported UIL. The adapter adds no hardware, game, or whole-program claim.

## Validation

Run the focused contract suite in a source checkout:

```sh
python -m pytest -q tests/test_c_frontend.py
```

With `clang` on `PATH`, the suite executes real AST imports, uses native Clang
results for signed and unsigned relation boundaries, and checks input-domain,
initialization, early-return, and unsupported-source behavior. It also passes an
authored fixture through the existing console C generator, the typed importer,
and native Clang execution, comparing every owned field on 256 input states.
Without Clang,
the compiler-dependent tests explicitly skip and the missing-compiler refusal
check remains active. A skipped run does not qualify the compiler path.

Keep compiler identity, selected source hash, source ABI, bindings, admitted
domain, and comparison boundary with any further evidence. The tests use
authored C fixtures and do not run original game code.
