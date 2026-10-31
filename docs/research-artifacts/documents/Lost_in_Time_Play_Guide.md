# Lost in Time — playable text and recovered native bilge

This continuation contains a complete **38-scene, 188-action authored text adventure**, plus a source-backed and replayed route through the original English game's hold and bilge. The text adventure is ready for a narrator to drive through a local JSON-lines process. The native route supplies recovered object coordinates, guarded scene actions, screenshots, VM observations and original-game checkpoints.

The latest fast recovery pass adds **51 source action descriptions, 23 targets, 12 source views and seven executable branch models**, including a newly lowered poster inspection. Two partial Z packages run through the pinned PR18 player. The measured rebuild and checks took **162.736 ms** from prepared source evidence; this excludes prior analysis and authoring. [PR #20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) contains the minimum acceptance contract and friction-removal requirements.

## Choose the experience

| Entry point | What it runs | Scope |
|---|---|---|
| `text/bridge.py` | The existing Zork-like adaptation | All 38 scenes; authored from the earlier guide/walkthrough work |
| `native_progress/bilge_native.py` | The original DOS game through fDisBull | A guided 35-stage hold/bilge route, with source and presentation checks |
| `bilge_text/play.py` | Six executable UIL branch models | Selected source responses and explicitly bounded puzzle effects |
| `fast_pipeline/z_poster_scene.json` | New poster branch through the pinned Z candidate | One source-profile scene action; all 256 counter values checked |
| `fast_pipeline/z_scene.json` | Six bilge models through the pinned Z candidate | Investigator entry states; partial, disconnected scene coverage |

The native route is an engineering qualification route, with its next supported command exposed. It is not a freely roaming original-game parser. The complete adaptation supplies the broader text game. They have separate authoritative state and explicit provenance.

## Play the text adventure

From the extracted archive root:

```bash
python3 lost-in-time/continuation/text/bridge.py --repl --save-dir ./lit-text-saves
```

Try `look`, `inventory`, `look behind barrel`, or `examine stool`. The runner also supports declared action phrases, exact action IDs, travel, `recap`, `undo`, `save` and `quit`. Resume with the same command plus `--resume`.

For a conversational narrator, omit `--repl` and send one JSON request per line:

```json
{"op":"observe"}
{"op":"execute","command":"a_find_lamp","context_token":"<current observed token>"}
{"op":"save","slot":"live"}
```

The narrator can privately inspect `catalogue` to map natural language to a declared action. It should narrate current observations and confirmed outcomes, ask when intent is ambiguous, and give hints only on request. The actual ChatGPT Live/voice connection has not been exercised; the local process interface is the integration boundary.

## Run the original-game route

Use the matching **fDisBull 0.22.0 offline kit** with Python **3.13.5**. The currently installed workspace interpreter is `tools/fdisbull-022-venv/bin/python`. The package's existing `Environment.txt` describes installing the separate kit and its local ncurses supplement; `native_progress/NATIVE_ROUTE_GUIDE.md` gives current commands and all route details.

Native checkpoints bind to the exact mount path and mounted files. At a new extraction location, create a new baseline:

```bash
LIT_ROOT="$PWD/lost-in-time/continuation"
LIT_PY="$PWD/tools/fdisbull-022-venv/bin/python"
"$LIT_PY" "$LIT_ROOT/native_progress/fresh_boot.py" \
  --game-dir "$LIT_ROOT/runtime/game" \
  --backend "$PWD/tools/fdisbull-dosbox" \
  --output "$PWD/lit-session"
"$LIT_PY" "$LIT_ROOT/native_progress/bilge_native.py" \
  --bootstrap "$PWD/lit-session/bootstrap-receipt.json" \
  --restore-mount --replay --output "$LIT_ROOT/native_progress/my-replay"
```

The fresh output directory must not already contain a session. Select the actual installed interpreter in `LIT_PY`. Omit `--replay` for JSONL control using `observe`, `execute`, `save` and `quit`. Native execution requires the current `context_token`. Unsupported actions, stale observations, wrong geometry and unqualified frames fail before another click; ambiguous delivery halts the route.

`--restore-mount` explicitly restores files matching the checkpoint before loading it and retains replaced bytes in `previous-mount/`. This matters because the guest changed `cat.inf` when closing. The host never modifies VM memory or invokes script handlers.

## Fast source → outline → UDL → UIL → Z

Read [fast_pipeline/README.md](fast_pipeline/README.md) for current-workspace rebuild and play commands. The investigator outline is `investigator_blueprint.json`; typed source obligations are in `udl.json`; seven executable models are in `uil.json`. The actual Z packages use the existing `fdisbull-il-scene-1` format from PR18 at commit `c107d1576d46d7dc353c8043cb81be5005e8926b`. That separate source checkout is required and is not included as an installed feature of the preserved 0.22 runtime.

The poster branch passed all 256 signed-byte counter cases, two guard refusals and unavailable-target rejection through the actual candidate backend. This establishes conditional source-profile agreement. Original DOS overflow behavior, all-state reachability and native click readiness were not newly tested. The broad 51-action descriptions remain execution-blocked until their dependencies are lowered.

These Z packages are investigator interfaces. Some bilge context IDs disclose hidden model state, so player-knowledge parity is unqualified. Use the complete authored adaptation for broad play. UDL → UIL here is a validated role-metadata copy; actual source lowering is measured separately.

## Retained native and authored-game verification

The following checks passed in the preceding continuation extension. The fast static pass reused their evidence and did not repeat the native route or full authored-game test run.

- Original-game replay: **35/35 stages**, comprising **30 fDisBull scene actions**, **one observed neutral UI gesture**, and **four explicit waits**.
- New-process native reopen: **4 checks passed**; drained water, consumed oil, corkscrew and visit history persisted; database integrity passed.
- Pure guard regression checks: **22/22 passed**, with recorded observations and labeled synthetic mutations; these are not manufactured native-game outcomes.
- Source UIL: **six programs**, **26 evaluator cases**, **five native retained-state comparisons** and **five JSONL CLI checks** passed.
- Full authored adaptation: **265 route transitions** and **eight verification categories** passed in the restored environment.

Evidence is under `native_progress/replay01/`, `native_progress/reopen01/`, `native_progress/guard_validation.json`, `native_progress/text_reverification.json` and `bilge_text/`. `qualified_reference/` is the separate reference-capture pass, not the strict replay receipt.

## Read next

- [Lost_in_Time_UIL_Contract.md](Lost_in_Time_UIL_Contract.md): representation, identity, coordinates and execution boundaries.
- [Lost_in_Time_Knowledge_Pack.md](Lost_in_Time_Knowledge_Pack.md): results, decisions, coverage and next work.
- [SOURCE_REPORT.md](bilge_source/SOURCE_REPORT.md): source offsets, recovered targets and limitations.
- [FAST_SOURCE_REPORT.md](native_progress/fast_source/FAST_SOURCE_REPORT.md): new hold targets, script inventory and measured decoding.
- [FAST_PROOF_REVIEW.md](native_progress/FAST_PROOF_REVIEW.md): independent final scope and identity review.
- [benchmark.json](fast_pipeline/benchmark.json): authoritative final pipeline measurements and coverage.
- [NATIVE_ROUTE_GUIDE.md](native_progress/NATIVE_ROUTE_GUIDE.md): complete launch and replay instructions.

The earlier unsaved 0.21 pilot was lost during workspace cleanup. This delivery extends a recovered 0.22 continuation and carries fresh verification. Its exact 0.21 files or historical check results are not claimed as recovered. Earlier reports retained inside the archive are historical evidence; this README and the new verification receipts describe the current extension.
