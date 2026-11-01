DOS reconstruction fixtures

learner/ contains only playable games, controls and licenses. Give ONLY these inner ZIPs to a blind reverse-engineering agent.
oracle/ contains original/adapted source and tests; do not give these to the learner.

Tic-tac-toe: documented NASM COM adaptation of ancient-tictactoe, not an exact upstream TASM/TLINK build. Three bounded native scenarios reported: invalid/occupied input, player-one win and draw. Full upstream equivalence unverified.

Five Dice: original simplified three-turn game (chance, highest pair, five of a kind), five dice, holds and up to three rolls. The host Python provider-injection demo supports LCG16 and xorshift16 bindings. It is NOT an actual UIL/UDC compiler or integration: no UIL artifact exists, and the DOS executable itself is not shown using interchangeable UDC bindings. Same draws are tested through scripted input; different RNG algorithms can legitimately give different outcomes. Modulo-six mapping is not an unbiased-dice proof; bounds/repeatability tests do not prove fairness.

Source packages retain concise test receipts; bulky original diagnostics remain in the producing cloud task. Nothing published publicly.
