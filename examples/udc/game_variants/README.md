# Selectable UDC game slices

These are authored examples for the current `fdisbull-il-1` and selected UDC
profiles. They exercise a fixed logical contract through three different
implementations: `clean`, `compact` and `verbose`. The native backing is generated
freestanding C, compiled into the existing Linux x86-64 ELF or Windows x64 PE
shell. The model backing uses the same persisted UDC selection and runs through
the UIL evaluator.

The Tic-Tac-Toe slice is a terminal notification decision. Inputs are `status`
(`0` ongoing, `1` win, `2` draw) and `player` (`0` none, `1` X, `2` O). Its output
`message` is `0` ongoing, `1` X wins, `2` O wins, `3` draw or `65535` for any other
typed pair. The native shell maps that code to a notification. It does not
check a board, choose a move or reproduce the earlier source-bound text patch.

The Five-Dice slice is a deterministic, authored 16-bit seed step:
`next = (5 * seed + 1) mod 65536`. A `fdisbull-module-uil-1` turn invokes five
selected steps and maps each result to a one-based face with `seed % 6 + 1`.
Each roll can choose a different backing. The native shell compiles the five
selected seed modules and calls them in order; the current native C profile
does not lower the module-UIL remainder operation, so the face projection is
verified by the model replay. The example makes no statistical, fairness or
original-game RNG claim.

Use a private fDisBull project outside this checkout. An existing project is
fine; the registration adds authored contracts/layers and does not change its
retained source bytes. For example:

```python
from fdisbull.project import Project
from examples.udc.game_variants import (
    register_game_variants, select_game_variants, replay_model,
    replay_compiled, build_native,
)

with Project('/private/work/example.fdb') as project:
    dice = register_game_variants(project, 'five-dice')
    styles = ['clean', 'compact', 'verbose', 'compact', 'clean']
    model = select_game_variants(project, dice, styles)
    turn = replay_model(project, model['id'], 'five-dice', seed=12345)
    faces = [turn['state'][f'$face{i}'] for i in range(1, 6)]

    compiled = select_game_variants(project, dice, styles, backend='c-uil')
    executed = replay_compiled(
        project, compiled['id'], 'five-dice',
        c_compiler='/absolute/path/to/clang', seed=12345,
    )
    assert [executed['state'][f'$face{i}'] for i in range(1, 6)] == faces
    build = build_native(
        project, compiled['id'], 'five-dice', '/private/new-dice-build',
        c_compiler='/absolute/path/to/clang', seed=12345,
    )
```

For Tic-Tac-Toe, pass a single style and the terminal inputs:

```python
ttt = register_game_variants(project, 'tic-tac-toe')
model = select_game_variants(project, ttt, 'compact')
message = replay_model(project, model['id'], 'tic-tac-toe', status=1, player=2)
# message['outputs'] == {'message': 2}

compiled = select_game_variants(project, ttt, 'compact', backend='c-uil')
executed = replay_compiled(
    project, compiled['id'], 'tic-tac-toe',
    c_compiler='/absolute/path/to/clang', status=1, player=2,
)
# executed['outputs'] == {'message': 2}
build = build_native(
    project, compiled['id'], 'tic-tac-toe', '/private/new-ttt-build',
    c_compiler='/absolute/path/to/clang', status=1, player=2,
)
```

`build_native` requires a new destination outside Git. It emits a selected
capsule containing the exact UIL, contract and layer IDs, qualification results,
compiler identity and output hashes. It does not execute the program. On a
matching Linux x86-64 host, the emitted `program` can be run with descriptor 3
redirected to a frame file; `fdisbull.udc_linux.decode_observation` decodes the
result. Windows builds use `target='windows-x64'` and their own execution
environment. The C source/object and model qualification are distinct from
native execution evidence.

`replay_compiled` is an example host runner for macOS arm64 or Linux. It reads
the persisted selection, qualifies each C backing against the fixed UIL model,
generates C with the UDC generator, compiles a temporary host library and calls
the selected function at each UIL invocation. It compares every compiled return
and output with the reference model and reports per-call source and library
hashes. A mixed Five-Dice turn therefore executes the selected C variant on
each roll, while the outer UIL handles its face projection. This host run is
separate from execution of the emitted PE or ELF shell.

The generated C for any selected module is available in the build result, for
example `build['c_modules']['terminal']['source']` or
`build['c_modules']['roll1']['source']`. Its source digest is recorded beside it,
so an A/B run can preserve the exact code that was compiled.

Run focused checks from the checkout; Z3 is part of the core install:

```sh
PYTHONPATH=src:. python -m pytest -q \
  tests/test_udc_tic_tac_toe_variants.py \
  tests/test_udc_five_dice_variants.py \
  tests/test_udc_game_variants_integration.py \
  tests/test_udc_game_variants_compiled_replay.py
```
