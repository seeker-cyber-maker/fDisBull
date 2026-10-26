# 0.15.0 local verification

This is working-tree candidate verification, based on `c5ed42e`, not a release
tag or a GitHub CI result. The source version is 0.15.0; published 0.14.0 assets
and existing DeepSeek deliveries remain unchanged.

## Real DinoPark, installed candidate wheel

The [parameterized driver](../examples/dinopark/verify_experiments.py) passed with
the original executable SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`, the pmm save,
and tested Mac native backend
`0876e686d6a85f8c1b790db03314b81f471f5a5791dcad4929b90b63a1ebeced`.
The driver imports the 0.15.0 wheel installed into a separate target directory,
and records its module path and driver hash. Package entries are checked against
the current source; no substitute dependencies or mock runtime are used.

The saved experiment survives closing the project and launching a fresh
emulator. The driver deliberately deletes its original controls, then verifies
an execution stop, eight read-watch bytes and a once-hook in both trials.
The baseline price read returns 7,500; the execution-layer read returns 5,000.
Final restoration re-arms the controls, restores the hook hit count to zero and
restores the baseline layer stack. Original code RAM, the price table and all
192 original/copied game files remain unchanged. Actual marked/clean frames,
two 16-record traces, intermediate register/stop observations and the comparison
are exported after project restart. States and the database remain private.

See the [result and claim boundaries](../examples/dinopark/evidence/experiments-0.15.0-2026-10-26/RESULT.md),
[comparison](../examples/dinopark/evidence/experiments-0.15.0-2026-10-26/comparison.json),
and [control/hook events](../examples/dinopark/evidence/experiments-0.15.0-2026-10-26/controls-and-hooks.json).
The catalogue's displayed list prices remain original. This acceptance concerns
the selected lookup and debugger workflow, not a complete purchase transaction.

## Native and failure-path acceptance

The Mac native command passed **60 tests, no skips**:

```bash
FDISBULL_DOSBOX=/absolute/path/to/layers/dosbox-x \
python -m pytest -q --require-native \
  tests/test_debug_experiments.py tests/test_debugger.py tests/test_code_layers.py \
  tests/test_ida_dosbox.py tests/test_screenshot_grid.py tests/test_render.py \
  tests/test_cfg_render.py
```

The new experiment cases cover project/session restart, normal and RAM-layer
baselines, execution overlays, write watches, consumed once-hooks, nonzero hook
hit counts, deleted breakpoints, native-ID rebinding, retained DOS CS contexts,
corrupt identities, partial hooks, untracked native controls, script failure
cleanup, offline CLI inspection, trace lookahead normalization and PNG/JSON
exports after restart. Original static instructions remain isolated.

A real custom Wine/QEMU experiment passed on the authored PE64 GUI fixture.
Its read/write watch stops before access; baseline and execution-layer trials
produce counters **8 and 10**, then restore **7**, the execution/data controls,
and baseline layers. The initial native test exposed a duplicate execution stop
when an INT3 was reinstalled at the saved PC. The correction verifies/reuses
the native control registry already captured by the whole-VM state, preserving
pending breakpoint displacement and page guards. The failing and corrected
receipts are retained locally. The corrected native test and selected authored
PE frames/traces are included in the evidence's `verification/` directory.
PE hooks, IDA experiments and outer-machine experiments remain unsupported.

The full Mac suite is **not green**: its final run reported **795 passed,
53 skipped, 2 failed and 23 fixture setup errors**. Those failures are the
existing Linux ELF compiler/linker fixtures under Apple's compiler, which emits
Mach-O or rejects ELF linker arguments. The focused native debugger gate above
passes. Native Mac verification does not qualify those Linux-only fixtures.

## Linux and package verification

The local Linux acceptance uses CPython **3.13.5**, an offline dependency
environment and the corrected source-built DOS backend. The initial reused
environment omitted declared managed test dependencies (`dnfile`/`dncil`), so
ten managed tests failed while its 58 native checks passed. Genuine pinned
managed wheels were added to a fresh run; the failed receipts remain separate.
The fresh final run passed **822 ordinary tests, 51 skipped**, and **60 native
tests, no skips**, with all installation and identity checks successful. The
native gate imported the installed 0.15.0 wheel (`pythonpath=`), not the source
checkout. Its backend SHA-256 was
`2aeb537ee7bbde674a72c759076bb26c3ba30fcc70ac5baa420bff0b07dc1e16`.
The ordinary skips cover optional native/toolchain inputs; the explicitly
required native gate has none. Package/exclusion and source-entry receipts
accompany the selected evidence.

The updated GitHub workflow includes the new DOS experiment tests in its
required Python 3.13.5 layers gate. The existing installed-wheel PE gate includes
the new real PE experiment test. Both GitHub Linux workflows must still run on
the eventual release commit before tagging. Local execution is not GitHub CI.

Tool packages exclude examples and experimental evidence by construction. The
wheel, sdist and tool ZIP are audited separately. Selected Git evidence permits
limited trace instruction bytes and screenshots; it contains no game files,
native states, databases, runtime images or compiled target fixtures.
