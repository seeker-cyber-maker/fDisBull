"""Authored metadata matching; these dictionaries are not native captures."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from examples.agi.dragon_boundary_witness import (
    WITNESS, describe_recorded_boundary, recorded_boundary_witness,
)


def report():
    return {
        'format': 'fdisbull-agi-spatial-predicates-1', 'complete': True,
        'source': {key: WITNESS['source'][key] for key in ('logic', 'resource_sha256')},
        'domain': {'width': 160, 'height': 168},
        'findings': [{
            'inside_if_offset': 0x3df, 'outside_if_offset': 0x432,
            'arguments': [0, 105, 96, 145, 166], 'convention': 'inclusive',
            'source_picture_sha256': WITNESS['source_picture_sha256'],
            'shared_scalar_context': {
                'matches_supplied_state': True,
                'conditions': [{'opcode': 1, 'arguments': [75, 0], 'negated': False,
                                'supplied_value': 0, 'matches': True}],
            },
            'action_contrasts': [{'item': 26,
                                 'inside': {'complete': True, 'linear_score_delta': -2},
                                 'outside': {'complete': True, 'linear_score_delta': 5}}],
            'bands': [{'predicate_band': {'complete': True, 'direction': 'down',
                       'thickness': 1, 'count': 41, 'row_runs': [[167, 105, 146]]}}],
        }],
    }


def match(value, **kwargs):
    args = {key: WITNESS['source'][key] for key in ('agi_sha256', 'object_sha256')}
    args.update(kwargs)
    return recorded_boundary_witness(value, **args)


def test_history_requires_independently_derived_matching_pattern_and_is_copied():
    value = report(); before = deepcopy(value)
    witness = match(value)
    assert witness == WITNESS and witness is not WITNESS and value == before
    witness['observed_points'][0]['origin'][0] = 0
    assert WITNESS['observed_points'][0]['origin'] == [130, 166]
    assert 'independent restored' in describe_recorded_boundary(match(value))
    assert describe_recorded_boundary(None) == ''


def test_recorded_metadata_matches_the_published_sanitized_pair():
    path = Path(__file__).resolve().parents[1]/WITNESS['evidence']['path']
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == WITNESS['evidence']['sha256']
    binding = json.loads(path.with_name('source-binding.json').read_bytes())
    assert binding['source_picture']['resource_sha256'] == WITNESS['source_picture_sha256']
    assert binding['paired_summary_sha256'] == WITNESS['evidence']['sha256']
    assert binding['source_picture']['matches_donor_capture'] is True
    witness = json.loads(raw)['witness']
    assert witness['source'] == {
        **{key: value for key, value in WITNESS['source'].items() if key != 'resource_sha256'},
        'logic_sha256': WITNESS['source']['resource_sha256'],
    }
    for recorded, native in zip(WITNESS['observed_points'], witness['forks'], strict=True):
        assert recorded['branch'] == native['branch']
        assert recorded['origin'] == [native['launch']['ego'][key] for key in ('x', 'y')]
        assert recorded['score_before'] == native['launch']['score']
        assert recorded['score_after'] == native['outcome']['score']
        assert recorded['water_consumed'] is True
        assert (native['launch']['item26_location'], native['outcome']['item26_location']) == (255, 0)


@pytest.mark.parametrize('field', ['agi_sha256', 'object_sha256'])
def test_other_source_cannot_inherit_historical_qualification(field):
    assert match(report(), **{field: '0'*64}) is None


@pytest.mark.parametrize('fault', [
    'partial', 'resource', 'picture', 'domain', 'offset', 'rectangle', 'context', 'unknown_context',
    'incomplete_effect', 'unknown_delta', 'different_delta', 'partial_band', 'other_band',
    'missing_findings',
])
def test_mismatched_or_incomplete_analysis_never_inherits_history(fault):
    value = report(); finding = value['findings'][0]
    if fault == 'partial': value['complete'] = False
    elif fault == 'resource': value['source']['resource_sha256'] = '0'*64
    elif fault == 'picture': finding['source_picture_sha256'] = '0'*64
    elif fault == 'domain': value['domain']['height'] = 169
    elif fault == 'offset': finding['inside_if_offset'] += 1
    elif fault == 'rectangle': finding['arguments'][-1] -= 1
    elif fault == 'context': finding['shared_scalar_context']['conditions'][0]['arguments'] = [74, 0]
    elif fault == 'unknown_context': finding['shared_scalar_context']['matches_supplied_state'] = None
    elif fault == 'incomplete_effect': finding['action_contrasts'][0]['outside']['complete'] = False
    elif fault == 'unknown_delta': finding['action_contrasts'][0]['outside']['linear_score_delta'] = None
    elif fault == 'different_delta': finding['action_contrasts'][0]['outside']['linear_score_delta'] = 6
    elif fault == 'partial_band': finding['bands'][0]['predicate_band']['complete'] = False
    elif fault == 'other_band': finding['bands'][0]['predicate_band']['row_runs'] = [[166, 105, 146]]
    elif fault == 'missing_findings': value['findings'] = []
    assert match(value) is None
