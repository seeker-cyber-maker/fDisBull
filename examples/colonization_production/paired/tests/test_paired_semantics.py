"""Authored semantic regressions, not a substitute for original CPU replay."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_uil import make, entry
from fdisbull.uil_runtime import execute_program
from fdisbull.common_uil import digest, validate_program, validate_presentation


def execute(edition, function, arguments):
    program, presentation, _ = make(edition)
    program, presentation = entry(program, presentation, function)
    return execute_program(program, presentation, inputs=arguments)


def values(edition, function, arguments):
    result = execute(edition, function, arguments)
    assert result['status'] == 'complete', result
    return result['outputs']


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_persisted_representation_matches_builder(edition):
    program, presentation, labels = make(edition)
    folder = ROOT / 'representations' / edition.lower()
    assert json.loads((folder / 'program.uil.json').read_text()) == program
    assert json.loads((folder / 'presentation.json').read_text()) == presentation
    assert json.loads((folder / 'labels.json').read_text()) == labels
    validate_program(program)
    validate_presentation(program, presentation)


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_capacity_complete_unsigned_byte_domain(edition):
    for level in range(256):
        assert values(edition, 2, [level]) == [100 * (level + 1)]


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_balance_resets_prior_accounting_and_wraps_before_comparison(edition):
    assert values(edition, 0, [4, 7, 2]) == [7, 3, 1]
    assert values(edition, 0, [4, 7, 5]) == [7, 3, 0]
    assert values(edition, 0, [32767, 0, 1]) == [0, 0, -32768]


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_net_preserves_unwritten_report(edition):
    assert values(edition, 1, [10, 3, False, 2, True, 99]) == [7, 99, False]
    assert values(edition, 1, [10, 3, True, 2, False, 99]) == [5, 99, False]
    assert values(edition, 1, [10, 3, True, 2, True, 99]) == [5, 2, True]


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_availability_is_strict_and_wrapped(edition):
    assert values(edition, 3, [4, 3, 7]) == [False]
    assert values(edition, 3, [4, 3, 6]) == [True]
    assert values(edition, 3, [1, 32767, 0]) == [False]


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_packed_field_nibble_order_and_signed_population(edition):
    assert values(edition, 4, [8, 0, 0xA5]) == [5]
    assert values(edition, 4, [8, 1, 0xA5]) == [10]
    assert values(edition, 4, [1, 1, 0xA5]) == [0]
    assert values(edition, 4, [-1, 0, 0xA5]) == [0]


def test_real_rule_difference_has_simple_nonoverflowing_witness():
    assert values('DOS', 5, [0, 0, 9, 3]) == [6, 6, 9, 0]
    assert values('WIN', 5, [0, 0, 9, 3]) == [6, 6, 6, 3]


def test_partial_supply_preserves_edition_specific_truncation():
    assert values('DOS', 5, [3, 0, 9, 3]) == [6, 3, 4, 5]
    assert values('WIN', 5, [3, 0, 9, 3]) == [6, 3, 3, 6]


def test_fully_supplied_and_nonbonus_cases_reconverge():
    for edition in ['DOS', 'WIN']:
        assert values(edition, 5, [6, 0, 9, 3]) == [6, 0, 0, 9]
        assert values(edition, 5, [0, 0, 9, 2]) == [9, 9, 9, 0]


def test_deleting_dos_correction_is_detected_not_normalized_away():
    p, v, _ = make('DOS')
    p, v = entry(p, v, 5)
    before = execute_program(p, v, inputs=[0, 0, 9, 3])
    changed = copy.deepcopy(p)
    # Set up + scale + balance call precede the DOS-only correction at index 4.
    del changed['functions'][5]['body'][4]
    changed_v = copy.deepcopy(v)
    changed_v['program_sha256'] = digest(changed)
    after = execute_program(changed, changed_v, inputs=[0, 0, 9, 3])
    assert before['status'] == after['status'] == 'complete'
    assert before['outputs'] == [6, 6, 9, 0]
    assert after['outputs'] == [6, 6, 6, 3]


@pytest.mark.parametrize('edition', ['DOS', 'WIN'])
def test_invalid_domains_are_not_guessed(edition):
    assert execute(edition, 4, [8, 32, 0xA5])['status'] != 'complete'
    assert execute(edition, 5, [0, 0, 9, 4])['status'] != 'complete'
    # Input admission raises before execution; failed in-program require returns refusal.
    with pytest.raises(ValueError, match='entry input type mismatch'):
        execute(edition, 2, [True])


def test_doc_labels_are_not_physical_addresses_or_execution_authority():
    p, v, names = make('DOS')
    old_p, old_v = copy.deepcopy(p), copy.deepcopy(v)
    names['production_input_pipeline']['slots'][0] = 'renamed_input'
    assert (p, v) == (old_p, old_v)
    assert p['format'] == 'fdisbull-common-uil-1'
    assert set(p) == {'format', 'capabilities', 'imports', 'functions', 'entry'}
