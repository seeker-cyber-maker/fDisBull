FIVE DICE - DOS x86 COM fixture, version 1
Run DICE.COM in DOS or DOSBox. One player; no files are saved. The initial
seed is fixed so replays are repeatable. This is a compact original game,
not a full Yahtzee implementation. License: CC0-1.0, see LICENSE.txt.

The game has three turns, categories in the fixed order SUM, PAIR, FIVE.
Each begins with five dice and one roll already used. Press 1-5 to toggle a
die's hold (1=held, 0=free); R rerolls free dice, at most twice; S records the
current category early or after the third roll. Invalid keys have no effect.
SUM scores the sum of dice; PAIR scores twice the highest matching pair, or 0;
FIVE scores 50 for five equal dice, or 0. Total is their sum. The on-screen
scorecard shows zero for unscored categories as well as actual zero scores;
the displayed turn identifies which have been completed. Game exits after
the third score.

This binary-only learner package intentionally omits source and oracle tests.
