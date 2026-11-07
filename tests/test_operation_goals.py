from copy import deepcopy
import json
from pathlib import Path

import pytest

from fdisbull.operation_goals import (
    load_operation_goals, operation_goal_schema, plan_operation, queue_frontier, validate_operation_goals,
)
from fdisbull.z_queue import DependencyQueue


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/synthetic/save-operation-goals.json'
SCHEMA = ROOT / 'src/fdisbull/data/operation-goals-1.schema.json'


@pytest.fixture
def document():
    return json.loads(EXAMPLE.read_text())


def refs(plan, section):
    return {(task['kind'], task['ref']) for task in plan[section]}


def test_semantic_save_goal_does_not_require_its_ui_realization(document):
    plan = plan_operation(document, 'SaveGame')
    assert {item['id'] for item in plan['operations']} == {'SaveGame'}
    assert not {'choose-slot', 'submit-request'} & {b['id'] for b in plan['known_blocks']}
    assert ('resolve-knowledge', 'actors-layout') in refs(plan, 'ready')
    assert ('recover-block', 'encode-globals') in refs(plan, 'ready')
    assert all(not task['ref'].startswith('ui-') for task in plan['ready'] + plan['blocked'])
    via_ui = plan_operation(document, 'SaveViaUI')
    assert {o['id'] for o in via_ui['operations']} == {'SaveViaUI', 'SaveGame'}
    assert ('resolve-knowledge', 'ui-slot-selection') in refs(via_ui, 'ready')
    # Recovery work is independent of the UI's execution order.
    assert ('resolve-knowledge', 'actors-layout') in refs(via_ui, 'ready')


def test_known_udl_and_opaque_region_identity_survive_goal_planning(document):
    original = deepcopy(document)
    plan = plan_operation(document, 'SaveGame')
    selected = {b['id']: b for b in plan['known_blocks']}
    assert selected['preserve-opaque'] == document['blocks'][4]
    assert selected['preserve-opaque']['signature'] == 'unknown'
    assert selected['preserve-opaque']['inputs'] == []
    assert selected['preserve-opaque']['udl_ref'] == 'udl:synthetic.preserve-opaque'
    assert plan['correspondences'] == document['correspondences']
    assert set(plan['unselected_blocks']) == {'choose-slot', 'submit-request'}
    assert document == original
    plan['known_blocks'][0]['resolution'] = 'resolved'
    assert document == original


def test_shared_blocks_and_missing_knowledge_are_deduplicated(document):
    duplicate = deepcopy(document['operations'][0]['steps'][0])
    duplicate['id'] = 'second-global-use'
    document['operations'][0]['steps'].append(duplicate)
    plan = plan_operation(document, 'SaveGame')
    assert sum(t['ref'] == 'encode-globals' for t in plan['ready']) == 1
    assert sum(t['ref'] == 'native-file-family' for t in plan['ready']) == 1
    assert len(plan['known_blocks']) == 6
    assert ('resolve-knowledge', 'completion-boundary') in refs(plan, 'blocked')
    assert ('resolve-knowledge', 'opaque-footprint') in refs(plan, 'blocked')


def test_new_findings_raise_coverage_without_proving_or_rewriting_blocks(document):
    before = plan_operation(document, 'SaveGame')
    document['findings'].append({'kind': 'block-result', 'ref': 'encode-actors',
                                'scope': 'candidate', 'evidence': ['candidate:actor-layout']})
    after = plan_operation(document, 'SaveGame')
    assert after['definition_sha256'] == before['definition_sha256']
    coverage = after['coverage'][0]
    assert 'encode-actors' in coverage['results_available']
    assert 'encode-actors' not in coverage['definition_resolved']
    assert coverage['scope'] == 'candidate'
    assert 'not semantic proof' in coverage['claim']
    actor = next(b for b in after['known_blocks'] if b['id'] == 'encode-actors')
    assert actor['resolution'] == 'opaque'
    assert ('recover-block', 'encode-actors') not in refs(after, 'ready') | refs(after, 'blocked')


def test_backward_frontier_unlocks_only_actual_knowledge_dependents(document):
    before = plan_operation(document, 'SaveGame')
    family = next(t for t in before['ready'] if t['ref'] == 'native-file-family')
    after = plan_operation(document, 'SaveGame', available=family['produces'])
    assert ('resolve-knowledge', 'completion-boundary') in refs(after, 'ready')
    assert ('resolve-knowledge', 'opaque-footprint') in refs(after, 'ready')
    assert ('recover-block', 'encode-actors') in refs(after, 'blocked')
    assert all(t['ref'] != 'native-file-family' for t in after['ready'] + after['blocked'])


def test_queue_frontier_can_complete_a_question_then_unlock_record_work(document, tmp_path):
    first = plan_operation(document, 'SaveGame')
    frontier = queue_frontier(first)
    queue = DependencyQueue(tmp_path / 'work.z.json')
    for task in frontier['tasks']:
        queue.add_task(**task)
    for fact in frontier['facts']:
        queue.publish(**fact)
    expected = set(frontier['ready'])
    assert {task['id'] for task in queue.ready()} == expected
    layout = next(t for t in first['ready'] if t['ref'] == 'actors-layout')
    queue.claim(layout['id'])
    queue.complete(layout['id'], outputs={layout['produces'][0]: {
        'value': {'scope': 'candidate', 'layout': 'synthetic-layout'}, 'evidence': 'candidate:layout-probe'}})
    reopened = DependencyQueue.load(tmp_path / 'work.z.json')
    second = plan_operation(document, 'SaveGame', available=set(reopened.snapshot()['facts']))
    assert ('recover-block', 'encode-actors') in refs(second, 'ready')
    assert not first['coverage'][0]['all_component_results_available']
    assert not second['coverage'][0]['all_component_results_available']


def test_complete_component_results_preserve_candidate_parent_scope(document):
    first = plan_operation(document, 'SaveGame')
    results = [key for task in first['ready'] + first['blocked']
               if task['kind'] == 'recover-block' for key in task['produces']]
    final = plan_operation(document, 'SaveGame', available=results)
    assert not final['ready'] and not final['blocked']
    assert final['coverage'][0]['all_component_results_available']
    assert final['coverage'][0]['scope'] == 'candidate'
    assert next(b for b in final['known_blocks'] if b['id'] == 'preserve-opaque')['resolution'] == 'opaque'


def test_changed_block_retires_only_its_dependent_fact_namespace(document):
    before = plan_operation(document, 'SaveGame')
    all_results = [key for task in before['ready'] + before['blocked']
                   if task['kind'] == 'recover-block' for key in task['produces']]
    document['blocks'][0]['udl_ref'] = 'udl:synthetic.changed-source'
    after = plan_operation(document, 'SaveGame', available=all_results)
    assert before['definition_sha256'] != after['definition_sha256']
    assert ('recover-block', 'encode-globals') in refs(after, 'ready')
    assert after['coverage'][0]['missing_results'] == ['encode-globals']


def test_unrelated_ui_definition_change_preserves_save_recovery_results(document):
    before = plan_operation(document, 'SaveGame')
    document['blocks'][-1]['region_ref'] = 'region:synthetic.changed-ui'
    after = plan_operation(document, 'SaveGame')
    assert before['definition_sha256'] != after['definition_sha256']
    assert before['ready'] == after['ready']
    assert before['available_fact_keys'] == after['available_fact_keys']


@pytest.mark.parametrize('change', [
    lambda d: d.update(extra='unsupported'),
    lambda d: d['blocks'].append(deepcopy(d['blocks'][0])),
    lambda d: d['blocks'][0].update(needs=['missing-question']),
    lambda d: d['operations'][0]['steps'][0].update(ref='missing-block'),
    lambda d: d['operations'][0]['steps'][0].update(inputs={'state': 'input:missing'}),
    lambda d: d['blocks'][0]['inputs'][0].update(type='incompatible-type'),
    lambda d: d['operations'][0]['steps'][0].update(after=['global-write']),
    lambda d: d['operations'][1]['steps'][-1].update(ref='SaveViaUI'),
    lambda d: d['knowledge'][0].update(needs=['globals-layout']),
    lambda d: d['blocks'][4].update(inputs=[{'id': 'invented', 'type': 'u32'}]),
    lambda d: d['correspondences'][0]['logical'].update(port='input:missing'),
])
def test_invalid_composition_or_unresolved_signature_is_rejected(document, change):
    change(document)
    with pytest.raises(ValueError):
        validate_operation_goals(document)


def test_json_schema_locally_resolves_and_matches_published_example(document):
    schema = json.loads(SCHEMA.read_text())
    assert schema['properties']['format']['const'] == document['format']
    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                assert value['$ref'].startswith('#/$defs/')
                assert value['$ref'].split('/')[-1] in schema['$defs']
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(schema)
    assert load_operation_goals(EXAMPLE) == document


def test_json_schema_with_independent_validator_when_available(document):
    jsonschema = pytest.importorskip('jsonschema')
    schema = operation_goal_schema()
    validator = jsonschema.Draft202012Validator
    validator.check_schema(schema)
    validator(schema).validate(document)
    document['blocks'][4]['inputs'] = [{'id': 'invented', 'type': 'u32'}]
    with pytest.raises(jsonschema.ValidationError):
        validator(schema).validate(document)
