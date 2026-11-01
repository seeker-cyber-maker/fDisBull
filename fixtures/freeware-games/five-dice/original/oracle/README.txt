FIVE DICE source and oracle, version 1. CC0-1.0; see LICENSE.txt.
This is separate from the binary-only learner package. It was authored for
this fixture; no upstream game source was incorporated.

Build: nasm -f bin dice.asm -o DICE.COM (tested NASM 2.16.03).
The DOS binary contains its own fixed-seed 16-bit LCG provider; changing the
host binding does not change the DOS binary. See learner README for controls
and scorecard. The source implements the documented game directly.

semantic-contract.txt is an experimental text contract, not valid fDisBull
UIL. demo.py is a small Python reference, NOT a fDisBull compiler, runtime,
or verified recovery of the native game. It shares the game rule model and
selects only the provider in binding-lcg.json or binding-xorshift.json:
  python3 demo.py binding-lcg.json 1 R R S S S
  python3 demo.py binding-xorshift.json 1 R R S S S
  python3 test_demo.py
Its provider owns a uint16 seed and state; a draw returns 1..6; each turn
requests dice in index order, skipping held indices. LCG16 uses wrapping
state = state*25173+13849; xorshift16 uses shifts 7, 9, 8 with 16-bit
masking. Both return state % 6 + 1. Zero seed is disallowed for xorshift.
Unknown providers, invalid seeds, script exhaustion and out-of-range scripted
draws raise ValueError, ending the experiment; no transaction is promised.
Modulo reduction is biased; these tests establish neither statistical quality
nor equivalence of distinct RNG streams. Same seed is not expected to yield
the same dice. Both binding runs share the exact same contract and game.py
implementation (here named demo.py); checksums are in evidence/host-tests.txt.
The scripted provider uses the same sequence twice to compare full transitions
and visible reference state, including holds, reroll limit, scoring and ending.

The supplied fDisBull 0.26.0 UDC DOS profile retains original native bytes,
and its semantic block profile is limited to straight-line register operations;
it cannot implement this RNG swap. This demonstration is not an executed UDC
binding and does not prove whole-game native/reference equivalence. Native
DOS tests drive real keyboard events and sample runtime memory; screenshots
and transcript are in evidence. Terminal memory was sampled at an exit breakpoint; after-exit.png shows
the final rendered score and game-over message after resuming execution.
