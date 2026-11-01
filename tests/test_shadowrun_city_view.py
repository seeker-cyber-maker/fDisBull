"""The view renders semantic fixtures, without private game imagery."""
from fdisbull.shadowrun_city_view import render_html
from fdisbull.shadowrun_world import SOURCE_SHA256


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
