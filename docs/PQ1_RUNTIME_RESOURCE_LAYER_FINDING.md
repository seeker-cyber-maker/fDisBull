# PQ1 runtime-resource layer finding

Status: open design/implementation finding

Observed: 2026-10-27

Tested fDisBull release: `v0.18.0` at `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae`

Current applicability: the relevant admission checks are unchanged on `main` at `2544b604bd5736d5f754fbdc2b099cd8905b609a`

## Summary

The DOS layer backend can atomically and reversibly change a guarded byte range
in conventional RAM, but the public persistent-layer API only admits addresses
inside regions derived from the imported MZ image and its declared allocation.
That is appropriate for code/data theories tied to the imported executable, but
it cannot represent a loaded game resource in an interpreter-managed runtime
heap.

Police Quest 1 exposed the distinction while testing an agent-facing observation
projection. Its AGI interpreter loaded the ego view from the game's volume into
runtime heap memory. A same-length transformation made all ego cels transparent
without changing their width, height, loop, mirror, timing or logical footprint.
The public layer definition rejected the loaded resource, while a bounded direct
backend transition applied and restored the same guarded bytes. The visible
frame before the transition and after restoration was byte-identical.

This is not evidence that arbitrary runtime heap memory should become a trusted
static project region. It is a concrete requirement for a separately authorized,
resolver-backed runtime-resource layer.

## Exact tested inputs

No game executable, volume, saved state, screenshot or project database is
included in this repository or pull request. The identities below permit an
authorized owner to identify the tested inputs without distributing them.

| Input | Identity |
| --- | --- |
| Game | Police Quest: In Pursuit of the Death Angel, AGI 2.917 |
| Original interpreter filename | `AGI` |
| Tested debugger alias | `AGI.EXE`, byte-identical alias required by the 0.18.0 nonempty-extension launch rule |
| `AGI` / `AGI.EXE` SHA-256 | `29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7` |
| `AGIDATA.OVL` SHA-256 | `f7ca256c1c0ab12509d695baabdd44a3c5e72a570b08118d3ead995a47f4c383` |
| Version evidence | `AGIDATA.OVL` contains the text `Version 2.917` |
| `VIEWDIR` SHA-256 | `e80e7b40535eeaad4b03141613a404329b7bbfd2fef0e9fd08a0a9da3ac457ce` |
| `VOL.0` SHA-256 | `04449e1da52628290906eee1fe81c0cbfdae7a6fb146dfda652c1a7dd6304e52` |
| View number | `0` |
| View resource offset | `VOL.0` offset `0x622f` |
| View payload length | 2,727 bytes |
| View payload SHA-256 | `61cd34f39eb9528b7cb3480878e166cf025dd30a65eaa1d12ac629792e19bba4` |
| Loaded view runtime address in the observed state | physical linear `0x1bce7` |
| fDisBull source | `0.18.0`, commit `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae` |
| DOSBox agent backend | macOS ARM64 Mach-O, SHA-256 `afa92bda2184e0c6f2fd685b164700058d212dd29b74af687de86234473d98d6` |
| Host used for the bounded probe | macOS 27.2, Darwin 27.2.0, ARM64 |
| Python used for this follow-up environment check | 3.13.13 |

The saved-state and runtime-address observations are specific to this tested
binary, resource set, backend and state. They are not proposed as universal AGI
addresses.

## Public failure

The imported MZ project admitted project addresses in its mapped allocation.
The loaded view was resolved through the running interpreter's data structures
and translated outside that static project region. Calling the public helper
with the exact live resource bytes and a same-length replacement failed before
creating or activating a saved layer:

```text
Layer patch must fit a mapped region; PE execution layers require code
```

The immediate checks are in `LayerProjectMixin.debug_layer()` and
`LayerSessionMixin._layer_address()`:

- a definition must fit a region returned by `project.regions(version)`;
- a live transition must also fit the mapped DOS allocation before translation;
- consequently a resource separately allocated by the interpreter cannot be a
  persistent public layer even when it is below `0xa0000` and its bytes are
  independently hash-bound to an authorized game resource.

The rejection is preferable to silently treating heap data as imported static
bytes. The gap is the absence of another explicit authority type.

## Bounded backend proof

The probe decoded the hash-bound view payload and found 20 cel definitions. It
preserved the resource length, all offsets and each cel's three-byte header,
including width, height, transparency and mirror fields. Only each cel's RLE
body was replaced with transparent row terminators.

Before the transition, the live 2,727 bytes were required to equal the admitted
view payload. The backend then applied one guarded paused RAM transition and
later restored the exact original payload with a second guarded paused
transition.

Observed effects:

- the ego became visually transparent while remaining logically present;
- the visible-to-transparent frame difference was 210 pixels, bounded to the
  ego rectangle `x=122..131`, `y=96..127`;
- the visible frame before enabling and after restoring the resource was
  byte-identical, SHA-256
  `f0962e7a4bef933d7c61e0aee3881169b3b9c1b00bae4c24d1f325779ae2debd`;
- the same admitted resource transformation was applied after loading a second
  game state, allowing ego-free comparison of two collectible object states;
- the public fDisBull project retained zero saved layer definitions from the
  rejected attempt.

This backend proof demonstrates byte-transition capability and the usefulness
of the projection. It does not establish a supported layer API, a durable
resolver, arbitrary-game compatibility or a safe raw-address interface.

## Proposed authority model

A runtime-resource layer should be a different authority from an imported-image
layer. A definition should bind to a resolver and immutable source identity,
not to one previously observed heap address.

One possible definition contract is:

```json
{
  "kind": "runtime-resource",
  "resolver": {
    "adapter": "agi-view-v1",
    "resource": {"directory": "VIEWDIR", "volume": "VOL.0", "view": 0},
    "source_sha256": "61cd34f39eb9528b7cb3480878e166cf025dd30a65eaa1d12ac629792e19bba4"
  },
  "replacement_sha256": "<same-length replacement>",
  "purpose": "transparent observation projection"
}
```

The exact schema and whether adapters live in fDisBull core or a consumer
package remain design decisions. The invariants should be:

1. Preserve the imported file bytes, static versions and prior evidence.
2. Resolve the live address in the current paused session; never persist an
   earlier heap address as sufficient authority.
3. Bind the resolver to exact source inputs, resource identity, adapter version
   and expected payload hash.
4. Require live bytes to equal the authorized base before enabling.
5. Require the replacement to have the same length unless a separate relocation
   mechanism is explicitly designed and tested.
6. Re-resolve after state restoration, resource unload/reload or a session
   restart.
7. Use the existing atomic paused transition and conflict guards once the
   resource has been admitted.
8. Restore only bytes still equal to the applied layer; preserve the existing
   changed-byte refusal semantics.
9. Record resolver inputs, resolved address, base and replacement hashes,
   backend identity, layer generation and restoration result.
10. Fail closed when resolution is ambiguous, bytes disagree, the resource is
    absent or restoration cannot be proven.

## Acceptance checks for a future implementation

A correction should include deterministic fixtures rather than PQ1 assets.

- A synthetic DOS interpreter allocates and copies a resource outside the
  imported MZ region.
- A resolver-backed definition admits the loaded copy from a hash-bound fixture
  resource and activates a same-length RAM layer.
- Enable/disable is atomic and restores the exact original bytes.
- A changed live byte rejects enable and does not partially transition.
- A changed applied byte rejects disable rather than overwriting guest state.
- Save-state restore and a simulated resource relocation cause re-resolution;
  a stale address is never patched.
- A wrong source hash, wrong resource number, ambiguous resolver result and
  unloaded resource fail without creating false authority.
- Restart preserves the immutable definition without preserving a stale
  address as trusted state.
- Existing imported-image RAM and execution layers retain their current API and
  verification behavior.
- Distribution checks confirm that no game files, states, databases or other
  proprietary probe artifacts enter packages.

An authorized PQ1 rerun may supplement those tests, but it should not be the
portable regression fixture.

## Non-goals

- Do not add PQ1, AGI, GOG or other proprietary payloads to fDisBull.
- Do not make every conventional-RAM address eligible for persistent layers.
- Do not encode `0x1bce7`, the ego record or another observed runtime address as
  a universal constant.
- Do not treat a visual change as proof that game logic, collision or proximity
  was changed.
- Do not expose raw diagnostic patching as a normal player capability.
- Do not weaken existing expected-byte, layer-conflict or restoration guards.

## Claim ceiling

This finding establishes one public admission failure and one successful,
reversible backend-level transition for the exact binary and resources listed
above. It motivates a resolver-backed runtime-resource authority. It does not
validate a proposed implementation or establish general interpreter/resource
support.
