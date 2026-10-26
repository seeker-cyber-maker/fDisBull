# DOS knowledge and observation-wait acceptance

26 October 2026. This is **uncommitted 0.16.0 working source**, based on main
`e91879c`. These local results do not claim GitHub CI, a tag, publication, or
acceptance in Pro's external environment.

The [sealed acceptance receipt](evidence/0.16.0-dos-knowledge/ACCEPTANCE.json)
records source hashes, exact package identities, commands/results and earlier
failures. Its [evidence manifest](evidence/0.16.0-dos-knowledge/MANIFEST.json)
binds the copied logs and XML files.

| Fresh check | Result |
|---|---|
| Linux x86-64 Python 3.13.5, complete ordinary suite | **1,065 passed; 59 skipped; no failures/errors** |
| Same interpreter, installed-wheel required native gate | **311 passed; no skips/failures/errors** |
| Installed package identity | All **89 fdisbull source/data entries** match the tested wheel |
| Mac affected-source regression selection | **315 passed** |
| Mac real DOS debugger/wait selection | **37 passed** |
| Separate comparison-alignment/incomplete-input checks | **14 passed** |

The native gate includes real DOSBox launches and pure decoding/contract checks;
311 is not a count of distinct game trials. It exercises original state restore,
breakpoints/watches, hooks/layers, screenshots, traces, experiments, the new wait
and a real call to the newly recognized Microsoft `strlen` returning 5 for
`hello`. Genuine offline decoder dependencies and the unchanged tested DOSBox
backend/private libraries were used, with networking disabled. The ordinary and
native gate identities point to the same wheel:

```
7fcc827a8a4fb89057db416a703c763f02c5c59cfc6f79178c0699816129b065
```

The wheel, sdist and tool ZIP passed exclusion audits. They contain the required
runtime catalog and Microsoft MIT notice; they contain no game executables or
resources, game saves, native states, project databases, VM images or compiled
target fixtures. The immutable tested packages are listed in the receipt;
these new verification notes are companion evidence. A later GitHub build needs
its own package identity/readback.

## Actual DinoPark

[The working driver](../examples/dinopark/verify_wait.py) saved/reopened a wait
script, observed immediate success with no guest execution, captured a failed
wait's diagnostic frame, restored the checkpoint and completed the existing
matched concession-price experiment. Execution breakpoint, eight watched read
bytes, once-hook/hit count and layers were restored. All 192 original and mounted
game files remained unchanged and child processes were reaped.

[Selected evidence](../examples/dinopark/evidence/observation-wait-0.16.0-2026-10-26/README.md)
includes the script, screenshots, 8 px grid, comparison and traces. States and
databases remain outside Git. The false wait requested 40 guest ms and measured
130; the 90 ms polling overshoot is recorded as failure, never successful
completion within budget. This does not reproduce E32 cancellation or establish
UI readiness from camera/frame/price observations.

A separate bounded static pass described 29 known service sites, including
file open/create/read/write/close. It remained partial with pending work and found
no qualified Microsoft runtime matches in that slice. The catalog supplies 182
variants covering 63 public names; it does not establish Borland/Pascal coverage.

## Failure history and boundaries

An initial Linux run passed 1,064 ordinary checks and failed two native checks:
the old 1,000-guest-ms/2,000-host-ms throughput assumption, and a diagnostic-frame
requirement in a short startup fixture. The success fixture now permits 10,000
host ms, and the screenshot fixture first establishes a genuine completed frame.
Strict timeout, overshoot and missing-capture tests remain in the suite. Requested
captures can still fail explicitly when the backend has no usable frame.

A later combined verification VM reached its outer deadline after ordinary
failed, before exporting the detailed log. An existing nested-layout regression
was independently reproduced from the exact pre-fix wheel: the new 8,192-node
limit rejected a legitimate 16 KB structure. The final implementation permits
65,536 nodes/members with a separate 4,096-instance union limit, and both that
existing test and the exponential-union guard pass. Gates now export results
independently. Earlier failures are retained; the final green results are fresh.

Comparison capture-count/identity hardening was verified separately with malformed
helper inputs. It is not inferred from E32 or the successful game route and does
not change the pinned 0.15.0 candidate already held by Pro.

The full Mac suite was not rerun; README retains its Linux-ELF fixture limitations.
Dedicated COM/SYS loaders, compiler-managed overlays, further compiler catalogs,
full interrupt coverage and external Pro-environment acceptance remain open.
