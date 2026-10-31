# Civ city UIL and executable UDC slice

Status: **partial, source-linked fixture with a natively executed macOS arm64 module;
not a whole-screen or whole-game parity claim**.

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
if not disorder:
    shield_box += shield_delta   # disorder preserves previously stored shields   # signed i16 semantics
```

`sanitized == true` means the caller has already applied the recovered source
boundary: reset `shield_box` to zero when it is below zero or above 999 before
production. The module does **not** reimplement that comparison because the
current shared UIL condition profile has no ordered comparisons. This avoids
turning the civd signed-storage/reset mismatch into a reachable-bug claim.

The module is therefore an executable bounded state transition, not a compiled
replacement for `city_process()`, the DOS VGA provider, or the Civ64 Windows
implementation.

## Native targets

`--target linux-x64` (default) emits a static ELF64 shell and reports
`native_execution: false` until a Linux runtime is supplied; on macOS that ELF
is a cross-target artifact and is not host-runnable without an external runtime.

`--target macos-arm64` uses the sweding profile
`macos-arm64-c-plan-libsystem-1`: the same UIL and typed state effects are
realized as generator-owned C compiled for `arm64-apple-macos11` and linked
against libSystem. Declared differences:

- machinery changes from fixed x86-64 slot lowering to C plus dyld/libSystem;
- observation is one JSON frame on stdout (no `capture_state` fd);
- the builder still records `native_execution: false`; execution is separate
  evidence.

Observed on this host for the default state:

```text
$ file /tmp/civ-city-macos-20261030/program
Mach-O 64-bit executable arm64
$ /tmp/civ-city-macos-20261030/program
{"format":"fdisbull-macos-observation-1","status":0,"value":0,
 "state":{"$shield_box":3,"$shield_delta":3,"$disorder":0,"$sanitized":1}}
```

That is the disorder-false branch adding the supplied contribution to a
sanitized box.

## Differential boundary sweep

`examples/civ/civ_city_udc_diff.py` builds one module per boundary state, runs
the emitted binary, and compares the observation frame with `execute_il` on the
primitive program. Every listed state agrees:

| case | initial state | interpreter | native arm64 |
|---|---|---|---|
| default | `box 0, delta 3` | `box 3` | `box 3` |
| wrap-high | `box 32767, delta 1` | `box -32768` | `box -32768` |
| wrap-low | `box -32768, delta -1` | `box 32767` | `box 32767` |
| negative-box | `box -5, delta 3` | `box -2` | `box -2` |
| disorder-preserves-stock | `box 7, delta 5, disorder` | `box 7` | `box 7` |
| unsanitized-refusal | `box 4, delta 2, sanitized false` | `status: refused` | exit 1, no frame |

`verdict: match` over the six states, with per-case artifact hashes in the
sweep receipt. Refusal is observable only as a nonzero exit with no observation
frame, because the program publishes state only on a committed transition.

Scope: this proves interpreter/native agreement for the tested states. It does
not prove that the UIL model matches the DOS routine, which the static trace
covers separately.

## BUY price, guard and commit module

`examples/civ/civ_city_buy_udc.py` models the city screen's buy path:

| stage | site | recovered behaviour |
|---|---|---|
| cost | `R:0D12:7399` / `R:0D12:73F6` | `production >= 0` reads unit word `[0x1142 + 0x22*id]`; `production < 0` reads improvement word `[0xBB2 - 0x1E*k]`, `k = -production`; both are shield cost / 10 at record offset `+0x18` |
| base | `R:0D12:73CD` | `ClampInt(10*cost10 - shield_box, 0, 999)` |
| price | `R:0D12:73D9` / `R:0D12:7430` | unit: `2b + i16(b*b)/20`; building: `2b` |
| doubling | `R:0D12:7446`, `R:0D12:7461` | buildings double when `k > 21`; both kinds double when `shield_box == 0` |
| guard | `R:0D12:75D2` | signed `treasury >= price`, else no purchase |
| commit | `R:0D12:75E5` | `shield_box := 10*cost10`, `treasury -= price` |

The IL gained `multiply` and `divide` for the quadratic (accumulate semantics
like `add`, wrapping into the destination type, truncating toward zero,
refusing a zero divisor), and `ge` now compares any integer cells as signed
64-bit values. All four realizations implement them: interpreter, C block
generator, macOS plan lowering and the x86-64 shell lowerer. On this host the
macOS path runs natively; the x86 path is verified by disassembling the emitted
`imul rax, rcx`, `cqo; idiv rcx` and `setge` sequences rather than by executing.

Native macOS arm64 sweep (`civ_city_udc_diff.py sweep_buy`) — interpreter and
emitted program agree on all eight:

| case | inputs | price | result |
|---|---|---|---|
| unit-default | `box 0, gold 1000, cost10 4, prod 0` | 320 | `box 40, gold 680` |
| unit-partial-stock | `box 10` | 105 | `box 40, gold 895` |
| unit-clamped-base | `box 100` (base clamps to 0) | 0 | `box 40, gold 1000` |
| unit-square-wrap | `box 0, cost10 30` | 3646 | `box 300, gold 1354` |
| unit-insufficient | `gold 100` | 320 | refused, exit 1, no frame |
| building-plain | `prod -2, box 0` | 160 | `box 40, gold 840` |
| building-doubled | `prod -22, box 0` | 320 | `box 40, gold 680` |
| building-stock | `prod -22, box 10` | 120 | `box 40, gold 880` |

`unit-clamped-base` is the `ClampInt` edge: a city holding more shields than
the item costs pays nothing.

`cost10` stays a module input because it comes from the two static tables,
which the IL carries as evidence rather than as data: the unit table costs are
verified against Civ1 (40/10/20/20/30/30/20/40/40/40/40/80) and the improvement
costs against Civ1 (Palace 200, Barracks 40, Granary 60, Temple 40,
Marketplace 80, Library 80), both divided by ten.

## Original-code correction gate

The former disorder branch zeroed storage instead of the contribution. Its own
interpreter/native sweep agreed on the wrong rule. That is now corrected, and
`civ_city_original_compare.py` separately executes the original signed reset
and accumulation instructions, evaluates UIL, then runs generated ARM64 code.
All 70 combinations agree, including nonzero stock during disorder, reset
boundaries, negative deltas and word overflow. Original spans remain unchanged.

```sh
PYTHONPATH=src:. python examples/civ/civ_city_original_compare.py /private/CIV_UNP.EXE /private/new-original-comparison
```

These are finite isolated-kernel observations. A city-entry provenance snippet
and a proof between two authored models do not establish source fidelity.
See the packaged `references/reconstruction.md` for the repeatable gate and
`docs/evidence/civ-original-corrections/verification.json` for sanitized results.
