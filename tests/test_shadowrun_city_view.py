"""The view renders semantic fixtures, without private game imagery."""
from fdisbull.shadowrun_city_view import render_html
from fdisbull.shadowrun_world import SOURCE_SHA256
import pytest


def test_city_view_keeps_precision_unknowns_and_escapes_embedded_data():
    state={'source_sha256':SOURCE_SHA256,'scene_id':2,'revision':'</script><script>bad()</script>',
           'player_x':1600,'player_y':3200,'camera_x':0,'camera_y':0,
           'bounds':[44,1876,44,1304],'terrain':bytes(2816),
           'captured_entities':[{'id':'actor.4','x':1601,'y':3202,'kind':11,'hp_byte_4c':10}]}
    html=render_html(state)
    assert '\\u003c/script\\u003e' in html and '</script><script>bad()' not in html
    assert 'No execution coordinate has been selected.' in html
    assert 'Visibility and walkability are unknown.' in html
    assert 'actor.4' in html and '1601' in html and '3202' in html
    assert "a.x===null||a.y===null" in html


def test_runtime_routes_only_declared_arena_presets(monkeypatch):
    from fdisbull import shadowrun_assisted_arena, shadowrun_city_view
    calls = []
    monkeypatch.setattr(shadowrun_city_view, '_read_rom', lambda path: b'rom')
    monkeypatch.setattr(shadowrun_city_view, 'captured_entities', lambda rom, snap: [])
    monkeypatch.setattr(shadowrun_city_view, 'ShadowrunRuntime',
                        lambda machine, captured_entities: machine)
    monkeypatch.setattr(shadowrun_city_view, 'machine_from_capture',
                        lambda rom, snap: calls.append(('static', snap)) or 'static')
    monkeypatch.setattr(shadowrun_assisted_arena, 'assisted_arena_from_capture',
                        lambda rom, snap, moving: calls.append(('arena', snap, moving)) or 'arena')
    assert shadowrun_city_view.open_runtime('rom', snapshot='cap') == 'static'
    assert shadowrun_city_view.open_runtime('rom', snapshot='cap', profile='assisted-arena',
                                            preset='moving') == 'arena'
    assert calls == [('static', 'cap'), ('arena', 'cap', True)]
    with pytest.raises(ValueError):
        shadowrun_city_view.open_runtime('rom', snapshot='cap', preset='moving')
