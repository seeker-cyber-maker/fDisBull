"""Authored receipt data only; no game or native execution."""
from copy import deepcopy
from hashlib import sha256
import math

import pytest
from fdisbull.scene_receipts import ReceiptAssembler, retain_evidence


RAW = b'authored frame bytes'
DIGEST = sha256(RAW).hexdigest()


def assembler(loader=None):
    return ReceiptAssembler({'sha256': 'a'*64}, {'policy': 'physical'}, loader or (lambda _: RAW))


def frame(index=1, path='frame.png'):
    return {'path': path, 'sha256': DIGEST, 'metadata': {'frame_id': index, 'mode_id': 5,
            'width': 320, 'height': 200, 'source': 'last_completed_guest_frame'}}


def obs(ident, index, count, **extra):
    return {'id': ident, 'state': {'score': count}, 'frame': frame(index),
            'input_count': count, 'message_count': 0, 'guest_ms': index*10, **extra}


def records():
    return [obs('before', 1, 0, frame_scope='last completed only'), obs('after', 2, 1)]


def test_frame_matches_existing_evidence_shape_and_caches_one_read():
    calls = []
    a = assembler(lambda path: calls.append(path) or RAW)
    original = frame()
    result = a.frame(original)
    assert result == {'sha256': DIGEST, 'metadata': original['metadata']}
    assert 'path' not in result
    result['metadata']['frame_id'] = 99
    assert a.frame(original)['metadata']['frame_id'] == 1
    assert calls == ['frame.png']
    with pytest.raises(ValueError, match='hash mismatch'):
        a.artifact({'path': 'frame.png', 'sha256': '0'*64}, 'other')
    assert calls == ['frame.png']


@pytest.mark.parametrize('change', ['bad_hash', 'bad_source', 'missing_frame', 'bool_frame', 'zero_width', 'loader'])
def test_invalid_frame_becomes_partial_without_losing_earlier_record(change):
    a = assembler((lambda path: (_ for _ in ()).throw(RuntimeError('unavailable'))) if change == 'loader' else None)
    data = records()
    if change == 'loader':
        # The first path remains available; the second fails.
        a = assembler(lambda path: RAW if path == 'frame.png' else (_ for _ in ()).throw(RuntimeError('unavailable')))
        data[1]['frame']['path'] = 'foreign.png'
    elif change == 'bad_hash': data[1]['frame']['sha256'] = '0'*64
    elif change == 'bad_source': data[1]['frame']['metadata']['source'] = 'unrelated'
    elif change == 'missing_frame': del data[1]['frame']
    elif change == 'bool_frame': data[1]['frame']['metadata']['frame_id'] = True
    elif change == 'zero_width': data[1]['frame']['metadata']['width'] = 0
    got = a.observations(data, expected_ids=['before', 'after'], input_count=1, message_count=0)
    assert got['complete'] is False and [x['id'] for x in got['observations']] == ['before']
    assert got['missing'] == ['after'] and got['issues']


def test_qualified_records_preserve_extras_strip_path_and_isolate_mutations():
    data = records(); a = assembler()
    result = a.observations(data, expected_ids=['before', 'after'], input_count=1,
                            message_count=0, require_progress=True)
    assert result['complete'] is True and result['issues'] == result['missing'] == []
    assert result['observations'][0]['frame_scope'] == 'last completed only'
    assert 'path' not in result['observations'][0]['frame']
    result['observations'][0]['state']['score'] = 999
    assert data[0]['state']['score'] == 0


@pytest.mark.parametrize('case', ['missing', 'extra', 'duplicate', 'order', 'regressed_frame', 'regressed_time',
                                  'same_time', 'nan_state', 'nan_time', 'counter_bool', 'counter_regressed', 'counter_short'])
def test_incomplete_evidence_is_not_silently_accepted(case):
    data = records()
    if case == 'missing': data.pop()
    elif case == 'extra': data.append(obs('extra', 3, 1))
    elif case == 'duplicate': data.append(deepcopy(data[0]))
    elif case == 'order': data.reverse()
    elif case == 'regressed_frame': data[1]['frame']['metadata']['frame_id'] = 0
    elif case == 'regressed_time': data[1]['guest_ms'] = 5
    elif case == 'same_time': data[1]['guest_ms'] = data[0]['guest_ms']
    elif case == 'nan_state': data[1]['state']['score'] = math.nan
    elif case == 'nan_time': data[1]['guest_ms'] = math.nan
    elif case == 'counter_bool': data[1]['input_count'] = True
    elif case == 'counter_regressed': data[0]['input_count'] = 1; data[1]['input_count'] = 0
    elif case == 'counter_short': data[1]['input_count'] = 0
    got = assembler().observations(data, expected_ids=['before', 'after'], input_count=1,
                                   message_count=0, require_progress=True)
    assert got['complete'] is False and got['issues']


def test_equal_frame_id_is_permitted_without_claiming_freshness():
    data = records(); data[1]['frame']['metadata']['frame_id'] = 1
    result = assembler().observations(data, expected_ids=['before', 'after'], input_count=1, message_count=0)
    assert result['complete'] is True
    assert 'fresh' not in result


def test_inputs_are_strict_and_deep_copied():
    data = [{'kind': 'keyboard', 'key': 'press:left', 'delivered': True, 'complete': True,
             'delivery': {'accepted': True, 'details': [1]}}]
    result = assembler().inputs(data); result[0]['delivery']['details'].append(2)
    assert data[0]['delivery']['details'] == [1]
    for key in ('delivered', 'complete'):
        bad = deepcopy(data); bad[0][key] = 1
        with pytest.raises(ValueError): assembler().inputs(bad)
    bad = deepcopy(data); bad[0]['delivery']['accepted'] = None
    with pytest.raises(ValueError): assembler().inputs(bad)
    with pytest.raises(ValueError): assembler().inputs([None])


def test_receipt_requires_explicit_completed_edges_and_preserves_private_roles():
    source = {'sha256': 'a'*64}; runtime = {'policy': 'physical'}
    a = ReceiptAssembler(source, runtime, lambda _: RAW)
    obs_result = a.observations(records(), expected_ids=['before', 'after'], input_count=1, message_count=0)
    catalog = [{'role': 'summary', 'visibility': 'public', 'sha256': 'b'*64, 'path': 'summary.json'},
               {'role': 'full-log', 'visibility': 'private', 'sha256': 'c'*64}]
    result = a.receipt(obs_result, edges=[{'id': 'go', 'before': 'before', 'after': 'after', 'complete': True}], artifacts=catalog)
    assert result['complete'] is True and 'authentication' in result['scope']
    assert result['artifacts'][1] == catalog[1] and 'path' not in result['artifacts'][1]
    assert a.receipt(obs_result, edges=[{'id': 'go'}])['complete'] is False
    assert a.receipt(obs_result, edges=[])['complete'] is False
    assert a.receipt({**obs_result, 'complete': False}, edges=[{'before': 'before', 'after': 'after', 'complete': True}])['complete'] is False
    result['source']['sha256'] = 'changed'; result['artifacts'][0]['path'] = 'changed'
    assert source['sha256'] == 'a'*64 and catalog[0]['path'] == 'summary.json'
    assert a.receipt(obs_result, edges=[{'before': 'before', 'after': 'after', 'complete': True}])['source']['sha256'] == 'a'*64


@pytest.mark.parametrize('edge', [
    {'complete': True},
    {'before': 'before', 'complete': True},
    {'before': 'unknown', 'after': 'after', 'complete': True},
    {'before': 'before', 'after': 'unknown', 'complete': True},
    {'before': 'after', 'after': 'before', 'complete': True},
    {'before': 'before', 'after': 'before', 'complete': True},
    {'before': True, 'after': 'after', 'complete': True},
    {'before': '', 'after': 'after', 'complete': True},
])
def test_edge_requires_retained_forward_endpoints(edge):
    a = assembler()
    observations = a.observations(records(), expected_ids=['before', 'after'])
    receipt = a.receipt(observations, edges=[edge])
    assert receipt['complete'] is False
    assert receipt['edges'] == [edge]
    assert any('forward order' in issue['reason'] for issue in receipt['issues'])


def test_forward_edge_may_span_intermediate_observation():
    a = assembler()
    observations = a.observations([obs('before', 1, 0), obs('middle', 2, 1), obs('after', 3, 2)],
                                  expected_ids=['before', 'middle', 'after'])
    edge = {'before': 'before', 'after': 'after', 'complete': True}
    assert a.receipt(observations, edges=[edge])['complete'] is True


@pytest.mark.parametrize('item', [{'role': 'summary', 'visibility': 'public', 'sha256': 'a'*64},
    {'role': '', 'visibility': 'private', 'sha256': 'a'*64},
    {'role': 'raw', 'visibility': 'unknown', 'sha256': 'a'*64},
    {'role': 'raw', 'visibility': 'private', 'sha256': 'nope'},
    {'role': 'summary', 'visibility': 'public', 'sha256': 'a'*64, 'path': '../private/log.json'},
    {'role': 'summary', 'visibility': 'public', 'sha256': 'a'*64, 'path': '/private/log.json'}])
def test_bad_catalog_records_are_rejected(item):
    a=assembler(); r=a.observations(records(),expected_ids=['before','after'])
    with pytest.raises(ValueError): a.receipt(r, edges=[{'before': 'before', 'after': 'after', 'complete': True}], artifacts=[item])


def test_identical_screenshot_can_be_referenced_privately_and_publicly():
    a=assembler(); r=a.observations(records(),expected_ids=['before','after'])
    items=[{'role':'screenshot','visibility':'private','sha256':'a'*64},
           {'role':'screenshot','visibility':'public','sha256':'a'*64,'path':'frame.png'}]
    assert a.receipt(r,edges=[{'before':'before','after':'after','complete':True}],artifacts=items)['artifacts']==items


def test_same_role_and_path_cannot_claim_different_bytes():
    a=assembler(); r=a.observations(records(),expected_ids=['before','after'])
    items=[{'role':'full-log','visibility':'private','sha256':'a'*64,'path':'log.json'},
           {'role':'full-log','visibility':'private','sha256':'b'*64,'path':'log.json'}]
    with pytest.raises(ValueError,match='conflicting hashes'):
        a.receipt(r,edges=[{'before':'before','after':'after','complete':True}],artifacts=items)


def test_retention_attempts_each_callback_and_preserves_primary():
    calls=[]; first=OSError('authored failure'); report={'error':{'message':'primary'},'complete':False}
    def fail():
        calls.append('first')
        raise first
    def succeeds():calls.append('second')
    result=retain_evidence((('save evidence',fail),('save receipt',succeeds)),report)
    assert calls==['first','second'] and result==[first] and result[0] is first
    assert report['error']=={'message':'primary'} and report['complete'] is False
    assert report['persistence_errors']==[{'operation':'save evidence','error':'authored failure'}]


def test_invalid_retention_operations_fail_before_any_callback():
    calls=[]
    with pytest.raises(ValueError):
        retain_evidence([('first',lambda: calls.append(1)),('second',None)],{})
    assert calls==[]


@pytest.mark.parametrize('call', [lambda: ReceiptAssembler({}, {'x': 1}, lambda _: RAW),
    lambda: ReceiptAssembler({'x': math.nan}, {'x': 1}, lambda _: RAW),
    lambda: ReceiptAssembler({'x': 1}, {'x': 1}, None),
    lambda: assembler().observations(None, expected_ids=['a']),
    lambda: assembler().observations([], expected_ids=['a', 'a']),
    lambda: assembler().observations([], expected_ids=['a'], input_count=True),
    lambda: assembler().observations([], expected_ids=['a'], require_progress=1),
    lambda: assembler().inputs([{}]*4097),
    lambda: assembler().artifact(None, 'frame')])
def test_invalid_api_arguments_raise_value_error(call):
    with pytest.raises(ValueError): call()
