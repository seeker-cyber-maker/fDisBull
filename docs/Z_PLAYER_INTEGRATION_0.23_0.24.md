# Z alongside the 0.23 compiler and proposed 0.24 work

Source review, 29 October 2026. The inspected compiler checkout is clean at
`ed89abca061964385b176537bc9fd275dd02afa5`, also observed on remote main.
Its version is 0.23.0. At the review's initial ref check, no `v0.23.0` tag was
advertised; source finalization, CI, publication and shared installation remain
separate observations. The shared native runtime used for these tests is the
retained 0.22.0 prefix. No versioned 0.24 specification was found in that source
or the recent inspected release conversation. The 0.24 items below are
recommendations, not promises from the release owner.

## What now matches

| 0.23 facility | Relationship to Z | Evidence or remaining boundary |
|---|---|---|
| Original-backed MZ/COM UDC | DinoPark's worker captures a definition and resources, calls the real compiler, checks its output, then drives the emitted original. | The committed compiler supplies the same APIs used by Z. The native retest uses that source, replacing the earlier private compiler snapshot. |
| Shared UDL/UIL representation | Z remains a consumer. UDL maps original code to UIL; UDC realizes UIL as code. | PR #18's pure UIL provider and PR #19's original-game provider share the player protocol. The native provider's Python handlers are adapters; they do not establish recovered UIL for every game effect. |
| Bounded ASM/C readers and Z3 | These can qualify future extracted handlers that Z exercises. | Current DinoPark uses zero semantic blocks and `original_bytes_only`. Register-boundary equivalence does not prove UI dispatch, memory effects, timing or a full game. |
| Immutable definitions and resources | Each play run starts with source/definition identities and a verified resource closure. | Game assets, compiler outputs, databases and native saves remain private. New paths are used for outputs. |
| Scenes, observations and input macros | Native Z actions reuse existing guarded scene transitions. | A matching image is distinct from control readiness and eventual effect completion. The bank change explicitly lets the guest consume cursor movement before its single press. |
| Agent guides and skill references | The new quickstart, CLAUDE/AGENTS entry points and selectively fetched references are useful discovery routes for Z. | After the Z PRs land, add a short player/content-provider route to the quickstart and bundled workflows reference; keep the human README focused on what can be played and tested. |
| Layer-by-layer native testing | Z supplies a convenient intent-level acceptance surface over the actual engine. | Keep compiler byte identity, a modeled block's proof, native observations and player outcomes as separate checks. A successful text sentence cannot substitute for a native commit. |

The inspection consulted 0.23's `docs/RELEASE-0.23.0.md`, `docs/UDC_DOS.md`,
`docs/UDC_TESTING.md`, `docs/AGENT_QUICKSTART.md`, the bundled
`references/udl-uil-udc.md` and `references/runtime-navigation.md`, and the recent
`Inspect fDisBull repo state` release turn. The occupied older main checkout was
also identified and left untouched; its uncommitted experiments are not the
0.23 release authority.

A three-way merge check of the committed Z branch against 0.23 main reports
one content conflict, in `README.md`. Keep 0.23's new human capability chooser
when integrating the Z PRs, and add a concise Z/DinoPark route there rather
than restoring the older release-oriented landing page. Runtime compatibility
is tested separately in a private combined 0.23 package. PR #19 remains stacked
on #18; the release checkout and other PRs are not edited by this change.

## Recommended 0.24 integration

1. **Make provider lifecycle a shared contract.** Distinguish clean EOF,
   cancellation, transport failure, forced kill and an unfinished run. Keep
   command outcome separate from process cleanup. Normal EOF may finish receipt
   writing; an uncertain request must stop without retry. The current patch
   supplies this behavior for the local process boundary. A next-release API
   should version its receipt format and expose opaque evidence handles for
   diagnostics without sending raw native memory to the model. Extend 0.23's
   selective skill-reference retrieval with bounded core output and artifact
   references; Z already bounds its public responses and keeps raw logs private.
2. **Represent input preparation below the intent.** A bank intent may need
   cursor movement, released-button checks, guest execution and a fresh scene
   assertion before a press. Keep those steps in its qualified native backing.
   Do not make every consuming player reconstruct them, or treat
   `click_button(ok)` and `loan_committed` as the same event. A future extracted
   effect can replace the input path only after its entry requirements, ABI,
   persistent effects and presentation behavior are established.
3. **Keep one public scene contract over different backings.** Zork text,
   DinoPark menus, an RTS selection panel and a spreadsheet cell can all expose
   objects and verbs. Native input, an isolated original snippet or a qualified
   UIL program supplies execution. Use an explicit provider/capability registry
   rather than creating a separate language or state simulation in Z. Retain
   partial coverage and stale-context rejection across providers.
4. **Journal asynchronous intent outcomes.** A Warcraft unit order or Dune II
   construction request can be accepted before the unit arrives or the building
   finishes. A spreadsheet recalculation can likewise remain pending after a
   command. Record input acceptance, effect commit, presentation completion and
   interruption separately. Preserve a confirmed purchase when its return
   animation or next scene fails. An unknown outcome must stay unknown.
5. **Give benchmarks an explicit run manifest.** Pin game/compiler/backend and
   scene-provider identities, initial native save, allowed assistance, coverage,
   guest-time budget, model/action limits and receipt policy. Score declared
   native postconditions, accepted actions and recovery behavior separately
   from narration. Use comparable budgets and record whether a replay used a
   native checkpoint or a fresh original loader. These tests establish a usable
   benchmark surface; they do not yet rank models.
6. **Define durable resumption separately from a live checkpoint.** DinoPark's
   disk writer and fresh OLD GAME loader already support the tested park. A
   live engine snapshot also depends on resource/disk identity and in-process
   ownership. A generic provider should advertise which kind it supports and
   invalidate stale context after either restoration.
7. **Grow compiler backings through qualified effect bindings.** Map an intent
   to its original-code identity, arguments, entry requirements, ABI, side
   effects and presentation obligations before substituting another backing.
   Compare Rust, JavaScript, Python or future DOS implementations against the
   same declared relation and native observations. Preserve earlier candidates
   and qualification limits when choosing an efficient implementation. The
   current bank adapter and byte-preserving UDC supply an experimental starting
   point; they do not establish an isolated native purchase function or a
   self-optimizing generic DOS compiler.

## Testing-agent testimony and immediate follow-up

Luna's initial 0.23 retest used the current Z player over the committed compiler
and actual original game. Two fresh bank cycles and a direct-original verifier
passed. Both old Z cycles nevertheless lacked the inner native receipt. This
was useful friction: public command success did not establish completed session
bookkeeping. The normal-close regression demonstrates that the old termination
path prevents an EOF finalizer; the new path allows it to finish.

For an agent, the useful working sequence is: inspect one bundled workflow,
select the correct compiler/native provider, issue public Z commands, and check
the named native postconditions and receipts. Keep the raw debugger available
inside the provider for qualification and diagnosis. Ordinary play does not
require the agent to reconstruct register queries or mouse coordinates each
turn. This is testimony about the exercised workflow, with the remaining bank
cause and coverage limits preserved in the reliability verification record.
