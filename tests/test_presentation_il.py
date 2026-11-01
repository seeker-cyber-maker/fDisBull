"""Behavioral checks for the authored, executable presentation UIL."""
import json
import pytest
from fdisbull.game_il import GameMachine, canonical, validate_program
from fdisbull import presentation_il
from fdisbull.presentation_il import lift_presentation, presentation_machine

SPANS = [(5, 7), (18, 12), (34, 12), (50, 13), (65, 14), (81, 14),
         (97, 14), (113, 14), (129, 14), (145, 14), (161, 14),
         (178, 12), (194, 12), (212, 8)]
INTERIOR = [(7, 2), (4, 8), (3, 10), (2, 12), (2, 12), (2, 13),
            (1, 14), (1, 14), (2, 13), (2, 12), (2, 12), (3, 10),
            (4, 8), (6, 4)]


def commit(machine):
    returns = []
    while machine.snapshot()['presentation_ready']:
        returns.append(machine.call('presentation_complete')['result'])
    return returns


def test_typed_uil_is_deterministic_and_has_no_private_regions():
    first = lift_presentation()
    assert canonical(first) == canonical(lift_presentation())
    assert canonical(first) == canonical(json.loads(presentation_il.ARTIFACT.read_bytes()))
    assert first['format'] == 'fdisbull-game-il-2'
    assert first['regions'] == []
    assert first['tree']['node'] == 'FileAST'
    validate_program(first)
    assert set(first['evidence']['entries']) <= set(GameMachine(first).functions)


def test_full_clear_and_ready_guard():
    m = presentation_machine()
    m.set_state({'presentation_staging': [i & 255 for i in range(296)],
                 'presentation_sparse': 1})
    assert m.call('presentation_prepare')['result'] == 1
    state = m.snapshot()
    assert state['presentation_count'] == 22
    assert state['presentation_jobs'][:22] == list(range(22))
    assert [state['presentation_chunk_end'][i] for i in (0, 7, 14)] == [7, 14, 22]
    assert m.call('presentation_prepare')['result'] == 0
    assert m.call('presentation_classify', 1, 0, 0)['result'] == 0
    assert m.call('presentation_terrain_miss')['result'] == 0
    assert m.call('presentation_clear_terrain')['result'] == 0
    assert m.snapshot() == state
    assert commit(m) == [0, 0, 1]
    assert m.snapshot()['presentation_active_nt'] == 1
    assert m.call('presentation_complete')['result'] == 255


def test_sparse_certificate_and_pause_fallback():
    m = presentation_machine()
    zero = [0] * 296
    m.set_state({'presentation_staging': zero, 'presentation_sparse': 1})
    for _ in range(2):
        assert m.call('presentation_prepare')['result'] == 1
        commit(m)
    assert m.snapshot()['presentation_sparse_valid'] == 3
    changed = zero.copy()
    for start, size in SPANS:
        changed[start:start+size] = [17] * size
    m.set_state({'presentation_staging': changed})
    m.call('presentation_prepare')
    assert m.snapshot()['presentation_jobs'][:14] == list(range(22, 36))
    commit(m)
    # Pause can dirty padding: it clears only the destination certificate.
    paused = changed.copy(); paused[0] = 33
    m.set_state({'presentation_staging': paused, 'presentation_sparse': 0,
                 'presentation_overlay': 1})
    m.call('presentation_prepare'); commit(m)
    # Populate a paused view into the other target too.
    m.call('presentation_prepare'); commit(m)
    assert m.snapshot()['presentation_sparse_valid'] == 0
    target = 1 - m.snapshot()['presentation_active_nt']
    m.set_state({'presentation_staging': changed, 'presentation_sparse': 1,
                 'presentation_overlay': 0})
    m.call('presentation_prepare')
    s = m.snapshot()
    assert s['presentation_target_nt'] == target
    assert 0 in s['presentation_jobs'][:s['presentation_count']]
    commit(m)


def test_cache_classification_and_clear_intersection():
    m = presentation_machine()
    m.set_state({'presentation_plane': [73] * 256,
                 'presentation_palettes': [19] * 256,
                 'presentation_staging_valid': 1,
                 'presentation_terrain_valid': 3})
    m.call('presentation_terrain_miss')
    s = m.snapshot()
    assert s['presentation_terrain_valid'] == 0
    assert s['presentation_staging_valid'] == 0
    kept = {row*16+x for row,(start,length) in enumerate(INTERIOR)
            for x in range(start,start+length)}
    assert len(kept) == 144
    for i in range(256):
        assert s['presentation_plane'][i] == (73 if i in kept else 0)
        assert s['presentation_palettes'][i] == (19 if i in kept else 0)
    for mode,ending,status,expected in [(1,0,0,1),(1,0,1,0),(1,3,0,0),(0,0,0,0)]:
        assert m.call('presentation_classify',mode,ending,status)['result'] == 1
        assert m.snapshot()['presentation_sparse'] == expected
        assert m.snapshot()['presentation_overlay'] == (status & 1)


def test_exact_cache_still_updates_hud_and_detects_overlay_change():
    m = presentation_machine()
    staging = [0] * 296
    m.set_state({'presentation_staging': staging, 'presentation_sparse': 1})
    for _ in range(2):
        m.call('presentation_prepare'); commit(m)
    # Both targets become certified for the same cached image.
    m.set_state({'presentation_terrain_cached': 1})
    for _ in range(2):
        m.call('presentation_prepare'); commit(m)
    assert m.snapshot()['presentation_terrain_valid'] == 3
    staging[256] = 7
    m.set_state({'presentation_staging': staging})
    m.call('presentation_prepare')
    state = m.snapshot()
    assert state['presentation_jobs'][:state['presentation_count']] == [16]
    commit(m)
    staging[5] = 80
    m.set_state({'presentation_staging': staging, 'presentation_overlay': 1,
                 'presentation_sparse': 0})
    m.call('presentation_prepare')
    state = m.snapshot()
    assert 0 in state['presentation_jobs'][:state['presentation_count']]


def test_oversized_budget_mutant_changes_full_partition():
    program = lift_presentation()
    def mutate(node):
        if isinstance(node, dict):
            if node.get('node') == 'Constant' and node.get('value') == '1218':
                node['value'] = '1392'
            for value in node.values(): mutate(value)
        elif isinstance(node, list):
            for value in node: mutate(value)
    mutate(program['tree'])
    m = presentation_machine(program)
    m.call('presentation_prepare')
    assert m.snapshot()['presentation_chunk_end'][0] == 8


def test_packaged_artifact_missing_or_modified_fails_closed(tmp_path, monkeypatch):
    original = lift_presentation()
    missing = tmp_path / 'missing.json'
    monkeypatch.setattr(presentation_il, 'ARTIFACT', missing)
    with pytest.raises(ValueError, match='missing or invalid'):
        lift_presentation()
    altered = json.loads(canonical(original))
    def change_budget(node):
        if isinstance(node, dict):
            if node.get('node') == 'Constant' and node.get('value') == '1218':
                node['value'] = '1392'
                return True
            return any(change_budget(value) for value in node.values())
        if isinstance(node, list):
            return any(change_budget(value) for value in node)
        return False
    assert change_budget(altered['tree'])
    altered_path = tmp_path / 'altered.json'
    altered_path.write_bytes(canonical(altered))
    monkeypatch.setattr(presentation_il, 'ARTIFACT', altered_path)
    with pytest.raises(ValueError, match='does not match'):
        lift_presentation()
    altered_path.write_text('{broken')
    with pytest.raises(ValueError, match='missing or invalid'):
        lift_presentation()
