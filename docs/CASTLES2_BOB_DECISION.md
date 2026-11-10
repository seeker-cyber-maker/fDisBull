# Decision record: Castles II BOB, capability versus workaround

**Date:** 2026-11-10. **Decision:** implement a narrowly selected "castles2-bob" media adapter in the existing fDisBull media APIs; do not create a separate graphics framework, codec registry, or generalized animation runtime. **Scope:** bitmap extraction and pixel fidelity on the inspected Castles II CD/GOG edition only.

## 1. Start from the friction, not the proposed technology

The 0.34.1 investigation could extract the original Castles II installer and run its original DOS Save/Load test, but the media adapter catalog had no way to decode ANIM.BOB. The missing BOB decoder blocks an immediate need: inspectable art for scene/visual-state study. It is not a global blocker to investigating or running the game.

Acceptance question: Can a user or test agent ask fDisBull to inspect a supplied original BOB resource and export original indexed pixels, RGB palette, and a viewable image through its existing safe output interface?

## 2. Exhaust existing capabilities before proposing a module

- Check "fdisbull media-modules", "media-inspect" and "media-extract". They already supply bounded immutable reads, source hashes, original byte offsets, manifests, private output safeguards, and an agent-visible catalog.
- Check the MADS IndexedImage class. It already models byte-indexed images with 8-bit RGB palette values and has a lossless PNG writer. Reuse it.
- Existing Westwood CPS, MADS sprite, and AGI picture decoders use incompatible on-disk formats. Do not deceptively feed BOB into one of them.
- The public Castles II modding page documents CLU and GAM formats but not this BOB bitmap. Public Steam depot metadata lists 97 BOB files. These are supporting context, not a format specification.
- The filename suffix ".BOB" is ambiguous across software. This particular variant contains no magic signature; require explicit selection plus strict geometry/length validation, not global extension-based detection.

External context: https://moddingwiki.shikadi.net/wiki/Castles_II%3A_Siege_and_Conquest ; https://steamdb.info/depot/670182/ .

## 3. Obtain structural evidence first

Independently examine representative user-supplied BOB resources, then every available resource before generalizing. For all **97 of 97** files in the supplied GOG CD edition:

| File range | Interpretation | Evidence |
| --- | --- | --- |
| 0..1 | width, unsigned 16-bit little-endian | plausible values in 97 files |
| 2..3 | height, unsigned 16-bit little-endian | plausible values in 97 files |
| 4..771 | 256 RGB888 triplets | visually coherent exported portraits and scenes |
| 772..EOF | one row-major 8-bit palette index per pixel | exact file-size equation for 97 files |

The exact file-size equation is **772 + width * height**, without trailing bytes, extra frames or compression. Corpus ranges: width 16..320, height 9..200; 28 distinct dimension pairs; 3,781,964 original BOB bytes. Interpret this as a **single-frame still bitmap** per file. Original-game alpha/color-key handling and frame-sequence timing remain unknown. Some portraits use magenta-looking backgrounds, but do not silently assign transparency to index 255.

## 4. Explicitly weigh need against cost and repeated effort

| Candidate | Implementation cost | Immediate value | Long-term value | Result |
| --- | --- | --- | --- | --- |
| View one image manually | Minimal | One image | Repeated rediscovery and no standard source receipt | Suitable for a truly one-off request |
| Private ad-hoc batch script | Low | Converts current 97 images | Not discoverable to another agent, lacks official source/output contract and permanent regression tests | Useful experimental oracle, not the permanent solution |
| **Small adapter inside existing media API** | **Low incremental**: one parser, one dispatcher/catalog entry, tests and skill reference; no dependencies or CLI changes | All 97 images and raw members with standard hashes | Avoids agent-by-agent reverse engineering; usable on the next Castles II investigation | **Chosen** |
| New generalized BOB/graphics/video engine | High: new registry, I/O policy, runtime/timing behavior, CI surface | No extra proven benefit | Hypothetical other games | Reject now |

The *actual measured corpus test* decoded, exported PNG, independently reopened/compared each pixel, checked each member digest, and rejected one truncated and one extended input per original. That took **4.079 seconds for 97 images**, or about **42 ms per asset including validation**. This is execution cost, **not** a measured estimate of agent minutes saved.

No accurate human/agent implementation time or repeated-manual-work time was collected, so do not invent ROI. The conceptual reuse break-even is ceiling(development+QA effort / manual rediscovery effort avoided per future investigation). The 97 immediate assets justify a small durable adapter; they do not justify a new media architecture. If a future target has one irrelevant BOB file, a local inspection may still be the better decision.

## 5. Minimal implementation and evidence contract

- Decoder is fdisbull.castles2_bob.decode_bob(bytes). It returns the existing MADS IndexedImage, requires exact byte length, positive dimensions <=4096 and <=4 MiB indexed pixels; other formats fail closed.
- Catalog advertises "castles2-bob" as explicit. Both existing media-inspect and media-extract accept it without new CLI commands.
- Members: "palette-rgb" (original bytes at 4), "indices" (original bytes at 772), and "preview-png" (derived bytes, no source offset). All are hash-bound to the source snapshot. Existing extractor creates a private directory and writes payload.bin plus media-manifest.json. The user can rename the PNG payload.bin to .png.
- No synthetic alpha, animation scheduling, palette cycling, runtime blit timing, original-game framebuffer equivalence, network download, subprocess or executing untrusted resource data.
- Authored fixtures only in Git: unit tests cover pixel/palette/PNG correctness, malformed/truncated/extra inputs, symlinks, media catalog/JSON/CLI routes, and private output semantics. The existing exact-name media-module regression expectation is updated alongside this feature.

## 6. Verified results and remaining qualifications

**Local:** 14 focused pytest cases passed on the installed 0.34.1 runtime patched with the adapter. The separate private real-game corpus check passed 97/97 exact layouts, 97/97 independent PNG colour comparisons, 97/97 media manifest checks, and 194/194 simple length-corruption refusals. PNG outputs and original game files remain private, not in this branch.

**Not established:** full repository test suite, release packaging, independent cold-agent QA, original game's compositing rules, animation timing, other games' BOB compatibility, or runtime visual equivalence. Hosted CI has not been triggered.

## 7. QA friction and next capability decisions

The name "payload.bin" for a PNG is a small existing generic extractor usability friction, not a reason to redesign its output contract in this targeted MR. The best immediate workaround is to rename the *private* derived file. If cold test agents repeatedly stumble, propose an explicit extension/format-aware output-name enhancement in its own review.

Do not overgeneralize: “ANIM.BOB” does not prove it holds a timeline. A magenta-looking palette value does not prove a colour-key instruction. Adding a game-specific compositing profile or animation scheduler needs a fresh original-execution observation, a value proposition and a separate scope choice.

Follow-up A/B QA: ask a cold agent to extract a BOB and report exact command/expectation/observation with the unchanged baseline, then repeat with the adapter. Retain tool-call count, time, first failure, resolution and transfer to an unrelated BOB-named file (which this adapter must not automatically recognize).

**General decision rule:** Prefer adding a small verified module when it solves a recurring observable problem, the existing framework cannot fulfill the contract without guessing, and reusable agent time is plausibly saved. Prefer a local experiment when only one immediate sample is needed. Escalate to a new engine only when a concrete consumer requires capabilities the current adapters cannot safely express.
