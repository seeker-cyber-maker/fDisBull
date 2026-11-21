# Persistent starting controls

Save learned keyboard and absolute mouse controls once and reuse them across
client connections and project/service reopen. Every invocation selects an
immutable source/version-bound revision in the independent DotBox store.
Existing fDisBull FDBs are preserved and refused; see [storage scope](STANDALONE.md#storage-and-scope). Legacy keyboard vocabularies keep using
the retained legacy keyboard document format; `dotbox-control-set-1` adds an explicit DotBox
control document in the DotBox control database. There is no mutable latest head.

This is the controls foundation of bounded preparation. It does not perform
autonomous discovery, recognize scenes, read an AGI interpreter or prepare a
complete starting Z buffer. The supplied vocabulary is explicitly authored for
the [input playground](../examples/input_playground.py), not a commercial game.
Resource-tree compatibility is not established by the executable binding.

## Prepare once

Start the [standalone service](STANDALONE.md) with the authored playground and a
compatible ownership-enabled DOSBox-X. In another tool call, observe its lease
and save the supplied left/right vocabulary:

```sh
python -m dotbox status --session /private/work/dotbox-session/session.json > /private/work/status.json
python -m dotbox harness-save \
  --definition /path/to/DotBox/examples/playground_controls.json \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/status.json > /private/work/controls.json
```

The result includes `result.revision`, a stable immutable ID. Saving the same
definition/parent again reuses its record. Saving only changes metadata: it
does not pause, resume or inject input, including when the human owns the game.
The request still needs a current service-instance/ownership lease.

Use the revision returned by that save explicitly below:

```sh
python -m dotbox harness-list --session /private/work/dotbox-session/session.json
python -m dotbox harness-info '<revision-id>' --session /private/work/dotbox-session/session.json
```

Default desktop mode uses the supported outer keyboard/mouse tools and refuses
native input RPCs, including `act`. Saved definitions record knowledge; they do
not by themselves implement an outer-tool executor or host-coordinate mapping.
For the selected intent, use a visibly applicable ordinary control immediately,
observe its effect, then
save it. Do not replay an action merely to give it a name.

## Explicit native diagnostic execution

The following commands require a service started with `--manual-control` and
an explicitly coordinated agent turn. They are not normal desktop-mode commands:

```sh
python -m dotbox control agent --resume \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/controls.json > /private/work/agent.json
python -m dotbox act '<revision-id>' move_left \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/agent.json
```

The action requires a running guest, current agent ownership and a fresh lease.
It never silently resumes a paused game. Accepted/queued input is not proof
that the game completed the intended interaction; observe a new frame to verify
the outcome. Built-in desktop takeover remains separate from this development
service's explicit native ownership.

## Add the next useful control

Edit an authored JSON vocabulary, then save it with
`--parent '<previous-revision-id>'`. This creates an immutable child revision;
it does not change an active head or rewrite previous work. Explicit sibling
branches are allowed. Every action selects the intended revision, so an older
usable vocabulary remains available after a new discovery.

Legacy `fdisbull-macro-set-1` keyboard definitions remain valid. For mouse
controls use `dotbox-control-set-1` with `controls` instead of `macros`:

```json
{
  "format": "dotbox-control-set-1",
  "name": "opening",
  "controls": {
    "open_panel": {
      "authority": "player-input",
      "steps": [{"op": "mouse.click", "x": 40, "y": 90,
                 "width": 320, "height": 200, "button": "left", "hold_ms": 80}]
    }
  }
}
```

Coordinates above are examples. `x,y` are absolute original guest-frame pixels,
not movement deltas or host-window coordinates. Expected `width,height` must
match at execution; a scene-specific action still needs an observed applicable
scene. Runtime frame/mode IDs are captured fresh, never persisted. A mouse
action contains exactly one click; mixed or multiple mouse steps are rejected
before effects. Keyboard-only actions retain bounded multi-step sequences.

The limits remain 32 controls per vocabulary, 16 keyboard steps and 1,000 ms of
queued input per control, and a 48 KiB definition. Text duration counts every
character. Runtime parameters, symbolic references, held-key leases, nested
macros, general debug scripts, memory operations and executable plugins are excluded.
Validation covers the whole vocabulary before saving and the complete selected
plan before its first input. Other tools' broader macro records cannot bypass
the smaller DotBox facade.

Each admitted step uses the ownership-aware backend primitive, including native
generation in the actual input RPC. A mouse `act` performs a bounded internal
pause, fresh-frame/dimension check, absolute click and explicit continue in one
request. It requires a running agent-owned guest and preserves unexpected stops
or ownership changes. No model inspection or recipe authoring occurs while this
transaction is paused. Returned coordination markers bracket requests and
responses; the continue acknowledgment is asynchronous, not exact resumed time.
Keyboard-only execution keeps its existing bounded path. A failure after earlier input returns
`action_interrupted` with acknowledged steps and the active step; effects may
already exist and are neither replayed nor claimed rolled back. Reobserve the
game before deciding what to do next.

## Reopen without rediscovery

Explicitly close the service, then start another service using the same project.
List/show the stored revision and execute it with the new service's lease.
The native game starts again; this slice retains learned controls, not a native
checkpoint. A lease from the old service is refused. Game checkpoint selection,
community package composition/import and complete scene preparation remain
later gates. Existing fDisBull exporters remain reusable foundations for sharing.

The native tests exercise metadata authoring in human-control mode, named input,
another client reusing a revision, incremental revision preservation, and controls
reused after full owner/guest shutdown. Real-game outcomes and interruption
timings remain separately scoped evidence; the earlier
[Dune trial](evidence/dune-local-terra-2026-11-15.json) predates persisted mouse actions.
The historical dependent-prototype [persisted-mouse retest](evidence/persisted-mouse-dune-2026-11-15.json)
verified five accepted actions and three visual transitions with a fresh local
Terra agent. It records the missed startup budget and distinguishes coordination
acknowledgments from exact guest pauses or complete player interruptions.
