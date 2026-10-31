# Civ city UIL and executable UDC slice

Status: **partial, source-linked fixture; not a whole-screen or whole-game parity claim**.

This document records the first concrete UIL/UDC realization of the city-screen
blueprint. It is intentionally narrower than `city_process()` and preserves the
edition conflict and source/runtime boundaries.

## UIL scene representation

The committed scene is:

- `examples/civ/civ_city_scene.json`
- `examples/civ/civ_city_scene.provenance.json`

It uses `fdisbull-il-scene-1` with a shared typed state projection:

| State | Type | Meaning | Boundary |
|---|---|---|---|
| `$view_mode` | `u8` | `INFO`, `HAPPY`, `MAP`, `VIEW` tab selection | Source-key/tab mapping only |
| `$city_size` | `i16` | population field | Declared state; no population transition |
| `$food_box` | `i16` | stored food | Declared state; no food pass |
| `$shield_box` | `i16` | signed stored production | Declared state; bounded UDC step below |
| `$production` | `i16` | unit/improvement selection | Catalog lookup not modeled |
| `$city_status` | `u8` | status bits; bit 0 is disorder | Bit 0 is exposed as a conditional object |
| `$city_owner` | `u8` | civilization slot | Declared state; no diplomacy/ownership effects |
| `$auto_build` | `bool` | automatic production flag | Display state only |

The scene inventory covers the city title, four tabs, food and production
storage, resources, the 21-tile radius, routes, buildings/wonders, units,
production controls, disorder status, rename and exit controls. Tab programs
are pure IL state/text transitions, so `ILSceneBackend` can observe and change
the selected tab without pretending to render VGA pixels.

`partial: true` is REQUIRED. The scene does not load original font/icon/map
assets, perform text entry, dispatch the production catalog, close a host
session, or implement the complete city turn pass. Objects without a binding
are visible inventory only, not silently executable controls.

## Bounded UDC module

`examples/civ/civ_city_uil.py` builds the module and a new Linux x86-64 shell.
The source input MUST be the exact generated unpacked root:

```text
SHA-256 aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57
```

Example, with private inputs outside Git:

```bash
PYTHONPATH=src python examples/civ/civ_city_uil.py \
  build/civ-analysis/CIV_UNP.EXE \
  /tmp/fdisbull-civ-city-udc \
  --project /tmp/fdisbull-civ-city-udc.fdb \
  --civd-citymgt /path/to/civd/src/CITYMGT.C \
  --civd-civ-h /path/to/civd/src/CIV.H \
  --civd-production-doc /path/to/civd/book/src/city/production.md
```

The builder:

1. Creates a private fDisBull MZ project from the unchanged unpacked bytes.
2. Captures 64 bytes at translated runtime address `1D12:0045`, the Civ64
   `R:0D12:0045` city-route seed under the MZ load segment `0x1000`.
3. Registers the exact typed contract
   `civ.city.production.sanitized-shield-step`.
4. Selects a shared-IL implementation and composes
   `fdisbull-module-uil-1` around the retained snippet identity.
5. Emits a new `fdisbull-native-shell-build-1` Linux ELF under a new output
   directory, with a selection capsule and hash-bound qualification receipt.

The modeled transition is deliberately preconditioned:

```text
require sanitized == true
if disorder:
    shield_box = 0
else:
    shield_box += shield_delta   # signed i16 semantics
```

`sanitized == true` means the caller has already applied the recovered source
boundary: reset `shield_box` to zero when it is below zero or above 999 before
production. The module does **not** reimplement that comparison because the
current shared UIL condition profile has no ordered comparisons. This avoids
turning the civd signed-storage/reset mismatch into a reachable-bug claim.

The module is therefore an executable bounded state transition, not a compiled
replacement for `city_process()`, the DOS VGA provider, or the Civ64 Windows
implementation. The native shell manifest reports `native_execution: false`
until a Linux x86-64 runtime is supplied; on macOS the generated ELF is a
cross-target artifact and is not host-runnable without an external runtime.

## Evidence and conflicts

The source-linked receipt keeps:

- Civd `CITYMGT.C`, `CIV.H` and production documentation hashes and exact
  commit `d9214fcd36aa6003d28aae60c3974b665f752280`.
- Civ64 analysis commit
  `4e46572d727544722d90c24dc2ce51a9c6d22f15` and the relative-to-runtime
  address translation.
- The pinned packed/unpacked executable identities.

The Civd label `474.05` and Civ64 label `475.05` still refer to the same packed
hash and remain `CIV-EDITION-001`; this slice does not resolve that conflict.

## Verification boundary

Fresh checks for this slice:

- `tests/test_civ_city_uil.py`: scene tab transitions, disorder/reset refusal,
  and pinned-source rejection.
- The builder was run against the exact unpacked root and produced a 32,768-byte
  ELF64 x86-64 executable with mode `0700`.
- fDisBull's shared-IL qualification status is
  `equivalent_under_contract`; that status qualifies the supplied model and
  selected layer, not source recovery or native runtime behavior.

Next required probe: trace a verified DOS caller/overlay path through the city
screen and compare one controlled state/display transition before promoting
any scene object from inventory to an executable game action.
