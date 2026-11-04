import json
from pathlib import Path

from test_z_controller import make_controller, SOURCE


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/synthetic/save-operation-goals.json'


def request(controller, verb, **params):
    reply = controller.handle({'verb': verb, 'params': params})
    assert reply['ok'], reply
    return reply['result']


def test_operation_goal_feeds_queue_and_completed_knowledge_unlocks_known_block(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    first = request(controller, 'operation-goal', document=str(EXAMPLE), goal='SaveGame', enqueue=True)
    retained = json.loads(Path(first['path']).read_text())
    assert 'encode-actors' in {b['id'] for b in retained['known_blocks']}
    assert not any(t['ref'] == 'slot-ui-contract' for t in first['ready'] + first['blocked'])
    question = next(t for t in first['ready'] if t['ref'] == 'actors-layout')
    request(controller, 'work-queue', op='claim', id=question['id'])
    request(controller, 'work-queue', op='complete', id=question['id'], outputs={question['produces'][0]: {
        'value': {'scope': 'candidate', 'layout': 'synthetic-layout'}, 'evidence': 'probe:actor-layout'}})
    second = request(controller, 'operation-goal', document=str(EXAMPLE), goal='SaveGame', enqueue=True)
    assert ('recover-block', 'encode-actors') in {(t['kind'], t['ref']) for t in second['ready']}
    assert second['definition_sha256'] == first['definition_sha256']
    assert second['path'] != first['path'] and Path(first['path']).exists()
    assert not session.calls
    assert not second['coverage'][0]['all_component_results_available']


def test_invalid_operation_goal_leaves_existing_queue_and_guest_untouched(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    request(controller, 'work-queue', op='add', id='existing', requires=[], produces=['existing-result'])
    queue_path = tmp_path / 'work.z.json'
    before = queue_path.read_bytes()
    document = json.loads(EXAMPLE.read_text())
    document['operations'][0]['steps'][0]['ref'] = 'unknown-block'
    failed = controller.handle({'verb': 'operation-goal', 'params': {
        'document': document, 'goal': 'SaveGame', 'enqueue': True}})
    assert not failed['ok']
    assert queue_path.read_bytes() == before and not session.calls


def test_conflicting_goal_frontier_merge_is_atomic(tmp_path):
    from fdisbull.operation_goals import plan_operation, queue_frontier
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    doc = json.loads(EXAMPLE.read_text())
    task = queue_frontier(plan_operation(doc, 'SaveGame'))['tasks'][-1]
    request(controller, 'work-queue', op='add', id=task['id'], requires=['unrelated'], produces=[])
    queue_path = tmp_path / 'work.z.json'
    before = queue_path.read_bytes()
    failed = controller.handle({'verb': 'operation-goal', 'params': {
        'document': doc, 'goal': 'SaveGame', 'enqueue': True}})
    assert not failed['ok']
    assert queue_path.read_bytes() == before and not session.calls
