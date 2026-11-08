# Menu/event structural discovery pilot

This extension is based on the retained 0.32.0 structural-discovery contribution,
not a claim about a released build or current integration branch. Original game
bytes, images, checkpoints, RAM, and detailed source-derived findings stay private.

## Two independent effect axes

The same control can mutate selected state, navigate to another interaction
context, do both, provide presentation feedback only, or remain unresolved.
Do not classify by its label, a CALL instruction, changed-pixel count, or a single
native scene ID. A new modal, selected page or caller continuation can change the
interaction context without allocating another world or loading another file.

`classify_episode` reports `context_effect` (same/changed/roundtrip/unresolved)
and `state_effect` (changed/unchanged-selected/unobserved/unresolved). Its category
is only a summary. Even a dispatch-effect with unchanged selected fields can have
unobserved state effects. An unknown destination or unready boundary is never
upgraded to local/no-op. A source context seen again after a sampled intermediate
context is a roundtrip, not no navigation. Unseen intermediate states remain a
sampling limitation. Pending state is caller-supplied evidence, not inferred
from elapsed time.

Before, idle and after observations must share original source/run/restoration
identity and retained evidence. Logical sample times must increase. Missing
fields are unknown, not cleared fields. Values that vary during the preceding
idle interval are reported separately; this is not a matched counterfactual
experiment and does not prove causation. Source-code consumers and controlled
replays provide stronger qualification.

## Entry points

The existing scan gains one shared rule without a title selector:

```sh
fdisbull structure-scan /private/extracted-input --output /private/new-leads --candidate-functions
fdisbull structure-info /private/new-leads/report.json --pattern selector-controls-operation --limit 3
python -m fdisbull.structure_events /private/retained-episode.json
```

`--candidate-functions` seeds heuristic prologues in addition to native entry
points. They are candidates, not proof of runtime reachability. Scan reports
retain source-view and budget qualifications. The episode command only reads a
bounded JSON file and prints a classification. It never replays source actions.
There is no `structure-events` top-level CLI verb or new public runtime schema.

## Code pattern and limits

`structure_events.selector_facts` consumes the already-decoded native rows.
It finds CMP-immediate followed by an adjacent JE/JNE whose flags are connected,
then follows each bounded single-entry arm to its first call, memory effect, or
return. Bindings include the selector expression/value, branch polarity, the
operation, the intervening source spans, and unresolved alternatives.

An iced-x86 length check agrees with Capstone for admitted rows. Overlapping
instruction candidates, joins, unknown operations, nested conditionals, loops,
and a call are barriers. A direct near jump within a qualified arm is followed.
An indirect call remains a call with unknown destination. An absolute number in
an operand is not assigned a game-specific semantic role.

The shared `selector-controls-operation` graph rule is applied alongside the
previous load-mask, dictionary, entity-mutation and indexed-decision rules.
The scan's rule-set hash includes the new rule. Code producers and the matcher
contain no title names, game offsets, control labels, or scene-number constants.

This is not a general callback registrar, queue/latch recognizer, cross-call
alias analysis, wait/resume solver, script-native linker, or automatic menu
crawler. It supplies useful dispatch *leads*. Deferred producer/consumer joins
still need explicit storage/owner/lifetime bindings and qualification.

## Original-menu experiment procedure

1. Reach an easily recoverable startup context using original input and bounded
   fast-forward. Verify it is waiting; attract loops and fades may continue.
2. Retain full reference frames, then calibrate stable text spans with the
   existing scene matcher. Exclude cursor, animation and unrelated background.
   Compare the resulting predicates against nearby/confusing states.
3. Record a preceding idle interval, then a fresh qualified pre-input state.
   Persist intent before dispatch. Require an owned stopped session and a
   source/run/restoration identity. Guard every admitted input.
4. Submit one input, and retain a bounded sparse-observation burst. Record
   actual guest ticks rather than assuming a requested millisecond slice was
   exact. Preserve state/request/presentation/readiness separately.
5. Follow an observed field to its original writer/reader or bind a code lead
   to a narrow instruction trace. Do not call ordinary code transfer navigation.
6. Repeat, include near misses, and propagate the general rule. Profile-specific
   coordinates, source identities and field bindings remain private data.

`examples/menu_event_probe/probe.py` implements steps 3–4 over an already-owned
session, caller-calibrated existing scene revisions, field readers and one
explicit input callback. It reuses `scene_check` and native `frame_probe`.
It is an experimental collector, not production automatic input authorization.
A readiness evidence string does not authenticate its claim. Input callbacks
and field readers are trusted investigator code, not actions loaded from target
data. Use normal `SceneHandle.act()` for established gameplay actions.

The collector journals intent and receipt separately and never retries after a
possibly accepted input. It checks session restoration identity at observations.
Multiple sparse checks occur while the guest is stopped; they are not a claim
that a graphical frame and every internal field share one atomic presentation
instant. The original renderer can lag the original state.

## Results of the bounded original-source experiment (2026-11-07)

Ultima IV TITLE: ordinary typing changes a selected name buffer while its prompt
remains. Backspace changes the stored last character to a space in the tested
case. Enter terminates/normalizes that buffer and returns to its caller, which
checks it and continues to a gender prompt. Surrounding-space input demonstrates
both mutation and navigation in one confirmation. A native data watchpoint
identified the original character write; its two instruction bytes independently
matched the source view. A 48-event original trace witnessed the Enter guard,
terminating store, cleanup, RET, caller test and subsequent call. Trace events
are before-fetch observations, not a proof that the final pending instruction
completed. Later original execution supplied the destination observation.

UFO: pointer Load and Cancel repeatedly navigate between the main menu and load
list. Intermediate observations can still match the source context or match no
registered context. The classifier preserves this history. Selecting an
apparently blank row subsequently reached the globe view, outside the calibrated
menu set. It stays unknown rather than a claimed no-op or successful save
restoration. No game-world state or loaded-save identity was qualified.

These are investigator-qualified profiles, not a cold-agent or autonomous
recognition evaluation. The native bodies remain original and no RAM was edited.
Full native checkpoint restoration was used within repeatable Ultima trials.
A subsequent generic profile runner launched each original in a fresh process:
four UFO dispatch operations and four Ultima local/dispatch/mixed operations
passed. The Ultima sequence restores a native checkpoint between its two name
variants. This is fresh-process replay of an already-qualified recipe, not
automatic menu discovery or a cold-agent trial.

Static source scans, two repetitions each, found 46 selector-operation matches
in Ultima TITLE, 481 in UFO GEOSCAPE and 556 in TFTD GEOSCAPE. They are short-arm
candidate matches, not unique buttons, callbacks, executable actions or complete
code coverage. Both protected-mode images hit the bounded instruction frontier.
TFTD did not receive a successful native menu test in this task: its attempted
explicit `C:` launch argument was refused by native DOS-token validation. That
refusal was not bypassed.

## Next qualification boundary

Recover an explicit pending-command or signal producer/consumer pair and its
owner/lifetime, then test the same rule on another implementation. Keep local
mutation and navigation independent; classify latch versus queue by behavior,
not the variable's name. Destination arrival does not by itself authorize a raw
scene-ID write or teleportation shortcut: original exit/entry effects still apply.

## Reproduce a qualified native profile

The source runner accepts an explicitly supplied private profile and original
executable directory. Scene bundles use the existing portable scene import,
including historical-reference labels and exact source/mapped-byte checks.
The private companion contains the two tested profiles and reference bundles.

```sh
python examples/menu_event_probe/replay_profile.py /private/profile.json \
  --game /private/extracted-original \
  --backend /private/qualified-dosbox-wrapper \
  --output /private/new-menu-run
```

The runner's launch-argument shim uses the existing native session.start channel;
it does not bypass native argument validation. For the supplied UFO layout, copy
the unchanged UFOEXE/GEOSCAPE.EXE into the root beside its resource directories
as the documented private launch alias, then use that root as --game. The
profile records argument 0, the normal GEOSCAPE menu entry rather than the full
intro-movie BAT chain. Ultima uses TITLE.EXE directly. Original installer
extraction and dependencies remain prerequisites. No Freeciv work is involved.

A caller-qualified profile is trusted experimental input, not a script mined
from game text. The bounded runner stops on mismatched source, guard, unexpected
native stop or outcome; it does not synthesize new routes or silently retry.
