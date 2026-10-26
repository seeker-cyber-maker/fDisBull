# DOS guest keyboard input

The 0.16.0 DOS backend accepts timed physical key presses through its emulated
IBM PC keyboard controller. It does not paste into a host window, write a BIOS
buffer or edit a game's name field. Python and saved scripts share the queue:

```python
debug.keyboard.type('Agent 16', hold_ms=40, gap_ms=40)
debug.run(guest_ms=1500, timeout_ms=5000, fast_forward=True)
debug.keyboard.press('backspace')
debug.run(guest_ms=150, timeout_ms=3000)
debug.keyboard.press('enter')
debug.run(guest_ms=150, timeout_ms=3000)
print(debug.keyboard.state())
```

`keyboard_press`, `keyboard_type` and `keyboard_state` are also available directly
on the DOS session. Server methods are `debug-keyboard-press`,
`debug-keyboard-type` and `debug-keyboard-state`. They require the owning `run`.

```json
{
  "format": "fdisbull-script-1",
  "steps": [
    {"op": "keyboard.type", "text": "Agent 16", "as": "input"},
    {"op": "run", "guest_ms": 1500, "timeout_ms": 5000},
    {"op": "keyboard.press", "key": "enter"},
    {"op": "run", "guest_ms": 200, "timeout_ms": 3000},
    {"op": "keyboard.state", "as": "keyboard"},
    {"op": "screenshot", "name": "after-name.png", "grid": true, "grid_step": 8}
  ]
}
```

Both durations are integer **guest milliseconds**, each 1..1000. Defaults are
40 ms held and 40 ms between keys. Text is limited to 64 characters per request:
printable US-layout ASCII, newline/carriage return (Enter) and Tab. Uppercase
letters and shifted punctuation generate actual Shift make/break events. A
different guest keyboard layout or Caps Lock state can change the characters.
Unicode and unsupported controls are rejected before injection.

`press` accepts lowercase letters, digits, unshifted punctuation, `enter`,
`escape`/`esc`, `tab`, `backspace`, `space`, arrows, `home`, `end`, `insert`,
`delete`, `pageup`, `pagedown`, `f1`..`f12`, `shift`, `ctrl` and `alt`.
Optional `modifiers=["ctrl", "shift"]` are pressed in order and released in
reverse order after the primary key. Duplicate or unknown modifiers are errors.

The response's `accepted: true, delivery: queued` means validated input was
queued, **not that the game consumed it**. `keyboard.state()` reports pending
events, owned keys and nominal queued guest time; elapsed time remaining in the
currently scheduled event is not measured. Only explicit execution advances the
queue. A breakpoint or hook can interrupt it; inspect that stop and resume
deliberately. A second operation is rejected while the queue is busy. No implicit
run bypasses a stop or timeout.

Native state saving rejects pending keyboard input, including direct state RPCs.
Loading a state or terminating/restarting a target cancels this adapter's queue
and releases its keys. Already consumed input and mounted-file writes are not
undone by cancellation. New native checkpoints use this new backend identity;
older backend hashes remain incompatible in project metadata.

The capability is `input.keyboard: ibm_pc_controller_us_ascii_v1`. Older DOS
backends fail clearly and must be rebuilt from either updated backend patch.
PE64 keyboard input and PC-98 keyboard injection are outside this addition.
Screenshots, traces and script results remain ordinary project artifacts. A
leaderboard entry is durable only after the actual game saves it and a fresh
session reads it back; queue acceptance and a typed dialog do not prove that.
