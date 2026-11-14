"""Independent algebraic obligations for the BLA numeric heap invariant.

These counterqueries do not execute target code and do not replace source-AST
admission. They check the mathematical facts used for indices, loop ranks and
the u31 numeric cells. Target code and heap values are intentionally absent.
"""

import pytest

z3 = pytest.importorskip("z3")

U31 = 0x7FFFFFFF
I32_MIN = -(1 << 31)
I32_MAX = (1 << 31) - 1
EXACT_INTEGER_MAX = (1 << 53) - 1


def unsat(*claims):
    solver = z3.Solver()
    solver.set(timeout=3000)
    solver.add(*claims)
    assert solver.check() == z3.unsat


@pytest.mark.parametrize("slot_count", [32, 48, 64])
def test_slot_access_and_cursor_update_preserve_bounds(slot_count):
    cursor, iteration = z3.Ints("cursor iteration")
    domain = [cursor >= 0, cursor < slot_count, iteration >= 0, iteration < 8]
    index = (cursor + iteration) % slot_count
    next_cursor = (cursor + 8) % slot_count
    unsat(*domain, z3.Or(index < 0, index >= slot_count))
    unsat(*domain, z3.Or(next_cursor < 0, next_cursor >= slot_count))
    # Nonnegative exact integer operands justify JS % using the same remainder.
    unsat(*domain, z3.Or(cursor + iteration < 0,
                        cursor + iteration > EXACT_INTEGER_MAX,
                        cursor + 8 > EXACT_INTEGER_MAX))


@pytest.mark.parametrize("bound", [8, 43])
def test_loop_rank_positive_decreases_and_reaches_zero_without_number_wrap(bound):
    counter = z3.Int("counter")
    domain = [counter >= 0, counter < bound]
    rank, next_rank = bound - counter, bound - (counter + 1)
    unsat(*domain, z3.Or(rank <= 0, next_rank < 0, next_rank != rank - 1))
    unsat(*domain, z3.Or(counter + 1 > EXACT_INTEGER_MAX, counter + 1 > bound))
    unsat(counter == bound, bound - counter != 0)


def test_unmasked_share_xor_preserves_u31_and_roll_is_positive_odd():
    share, mask = z3.BitVecs("share mask", 32)
    roll = (mask & 0x7FFF) | 1
    next_share = share ^ roll
    unsat(z3.Extract(31, 31, share) == 0,
          z3.Extract(31, 31, next_share) != 0)
    unsat(z3.Or(z3.ULT(roll, 1), z3.UGT(roll, 0x7FFF), (roll & 1) != 1))


def test_masked_word_epoch_tag_and_frontier_updates_preserve_u31():
    word0, word1, word2, word3, mix, epoch, tag, frontier, mask = z3.BitVecs(
        "word0 word1 word2 word3 mix epoch tag frontier mask", 32)
    iteration = z3.BitVec("iteration", 32)
    expressions = [
        (word0 ^ mix) & U31,
        ((word1 + word0) ^ z3.LShR(mix, 3)) & U31,
        (word2 ^ word1 ^ 0x27D4EB2D) & U31,
        ((word3 ^ word2) + iteration) & U31,
        (epoch + 1) & U31,
        (tag ^ word0) & U31,
        (frontier ^ (mask + 1147)) & U31,
        (mask ^ 0x5BD1E995) & U31,
    ]
    for value in expressions:
        unsat(z3.Extract(31, 31, value) != 0)


@pytest.mark.parametrize("frontier_count", [28, 32])
def test_number_additions_are_exact_safe_integers(frontier_count):
    a, b, mask, iteration, frontier_index = z3.Ints("a b mask iteration frontier_index")
    domain = [a >= 0, a <= U31, b >= 0, b <= U31,
              mask >= I32_MIN, mask <= I32_MAX,
              iteration >= 0, iteration < 8,
              frontier_index >= 0, frontier_index < frontier_count]
    additions = [a + 1, a + b, a + iteration, mask + frontier_index * 37]
    for value in additions:
        unsat(*domain, z3.Or(value < -EXACT_INTEGER_MAX, value > EXACT_INTEGER_MAX))


def test_dropped_share_roll_mask_has_a_real_range_counterexample():
    # The actual share XOR has no final u31 mask. Its restricted roll is needed.
    share, unrestricted_roll = z3.BitVecs("share unrestricted_roll", 32)
    solver = z3.Solver()
    solver.set(timeout=3000)
    solver.add(z3.Extract(31, 31, share) == 0,
               z3.Extract(31, 31, share ^ unrestricted_roll) == 1)
    assert solver.check() == z3.sat


def test_dropped_slot_remainder_has_an_out_of_bounds_counterexample():
    cursor, iteration = z3.Ints("cursor iteration")
    solver = z3.Solver()
    solver.set(timeout=3000)
    solver.add(cursor >= 0, cursor < 32, iteration >= 0, iteration < 8,
               cursor + iteration >= 32)
    assert solver.check() == z3.sat
