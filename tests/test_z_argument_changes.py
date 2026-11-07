from copy import deepcopy
import json

import pytest

from fdisbull.z_argument_changes import summarize_argument_changes


def sample(register, value, address=0x4000):
    return {'register': register, 'value': address,
            'pointer_hypothesis': {'address': address, 'hex': value.hex(), 'bytes': len(value)}}


def compare(old, new):
    return summarize_argument_changes({'arguments': [sample('EAX', old)],
                                       'post_arguments': [sample('EAX', new)]})['comparisons'][0]


def test_integer_change_is_only_a_byte_candidate_and_does_not_mutate_input():
    contract = {'arguments': [sample('EAX', (13).to_bytes(4, 'little'))],
                'post_arguments': [sample('EAX', (99).to_bytes(4, 'little'))]}
    original = deepcopy(contract)
    summary = summarize_argument_changes(contract)
    row = summary['comparisons'][0]
    assert row['status'] == 'changed'
    assert (row['bytes_compared'], row['bytes_changed']) == (4, 1)
    assert row['first_u32_le'] == row['first_i32_le'] == {'before': 13, 'after': 99}
    assert row['changed_ranges'] == [dict(offset=0, length=1, before_hex='0d', after_hex='63', omitted_bytes=0)]
    assert 'meaning are not inferred' in summary['claim']
    assert contract == original


def test_signed_candidate_and_aliases_are_preserved_without_double_counting():
    old, new = b'\xff' * 4, b'\x01\x00\x00\x00'
    summary = summarize_argument_changes({
        'arguments': [sample(name, old) for name in ('EAX', 'EDX')],
        'post_arguments': [sample(name, new) for name in ('EDX', 'EAX')]})
    assert len(summary['comparisons']) == 1
    assert summary['comparisons'][0]['registers'] == ['EAX', 'EDX']
    assert summary['comparisons'][0]['first_i32_le'] == {'before': -1, 'after': 1}
    assert summary['bytes_compared'] == summary['bytes_changed'] == 4


@pytest.mark.parametrize('after', [None, {'register': 'EAX', 'pointer_hypothesis': None},
    {'register': 'EAX', 'pointer_read_error': 'unreadable'},
    {'register': 'EAX', 'pointer_read_error': '', 'pointer_hypothesis': {
        'address': 0x4000, 'bytes': 3, 'hex': '616263'}}])
def test_missing_or_unreadable_post_is_unobserved(after):
    summary = summarize_argument_changes({'arguments': [sample('EAX', b'abc')],
                                         'post_arguments': [] if after is None else [after]})
    row = summary['comparisons'][0]
    assert row['status'] == 'unobserved'
    assert row['bytes_compared'] == row['bytes_changed'] == 0
    assert row['unobserved']['after']


def test_missing_before_and_pointer_address_mismatch_never_mean_unchanged():
    row = summarize_argument_changes({'post_arguments': [sample('EAX', b'ab')]})['comparisons'][0]
    assert row['status'] == 'unobserved'
    row = summarize_argument_changes({'arguments': [sample('EAX', b'ab')],
        'post_arguments': [sample('EAX', b'ab', address=0x5000)]})['comparisons'][0]
    assert row['status'] == 'not_comparable'
    assert row['reason'] == 'pointer_address_mismatch'
    assert row['bytes_compared'] == 0


def test_unequal_lengths_compare_only_prefix_and_keep_missing_tail_explicit():
    row = compare(b'abcde', b'abc')
    assert row['status'] == 'partial'
    assert row['bytes_compared'] == 3 and row['bytes_changed'] == 0
    assert not row['comparison_complete']
    assert (row['before_uncompared_bytes'], row['after_uncompared_bytes']) == (2, 0)
    assert compare(b'abcde', b'axc')['status'] == 'changed'
    assert compare(b'abc', b'abc')['status'] == 'unchanged'


def test_changed_range_previews_and_omission_counts_are_bounded():
    row = compare(bytes(256), bytes([1]) * 256)
    assert row['changed_range_count'] == 1
    assert row['changed_ranges'][0]['length'] == 256
    assert len(row['changed_ranges'][0]['before_hex']) == 32
    assert row['changed_ranges'][0]['omitted_bytes'] == row['omitted_changed_bytes'] == 240
    row = compare(bytes(256), bytes([1, 0]) * 128)
    assert row['bytes_changed'] == row['changed_range_count'] == 128
    assert len(row['changed_ranges']) == 4
    assert row['omitted_ranges'] == row['omitted_changed_bytes'] == 124
    assert len(json.dumps(row)) < 2000


def test_invalid_sample_is_unobserved_and_input_size_is_bounded():
    row = compare(b'a' * 257, b'a' * 257)
    assert row['status'] == 'unobserved'
    with pytest.raises(ValueError, match='at most 7'):
        summarize_argument_changes({'arguments': [sample(str(i), b'a') for i in range(8)]})
    with pytest.raises(ValueError, match='duplicate'):
        summarize_argument_changes({'arguments': [sample('EAX', b'a'), sample('eax', b'a')]})


def test_alias_address_alone_cannot_hide_different_captured_bytes():
    summary = summarize_argument_changes({
        'arguments': [sample('EAX', b'abcde'), sample('EDX', b'abcde')],
        'post_arguments': [sample('EAX', b'abcdf'), sample('EDX', b'abcde')]})
    assert [row['status'] for row in summary['comparisons']] == ['changed', 'unchanged']
    assert 'first_u32_le' not in summary['comparisons'][0]
