"""Dot-mode serves retained frames only; it has no guest/host input endpoint."""
import urllib.error
import urllib.request

import pytest

from test_windows_scenes import program


def get(url,**kwargs):
    with urllib.request.urlopen(urllib.request.Request(url,**kwargs),timeout=2) as response:
        return response.status,response.read(),response.headers


def test_dot_mode_is_explicit_read_only_and_viewer_requests_do_not_touch_native_session(program):
    assert program.dot_mode()['enabled'] is False
    state=program.dot_mode(True);assert state['view_only'] and state['host_input_capture'] is False
    assert state['host_keyboard_forwarded'] is state['host_mouse_forwarded'] is False
    url=state['viewer_url'];before=list(program.calls)
    status,page,headers=get(url)
    assert status==200 and b'Dot-mode spectator' in page and b'Host keyboard and mouse are never forwarded' in page
    assert b'<script' not in page and b'pointerLock' not in page and b'onkeydown' not in page and b'onclick' not in page
    assert headers['Cache-Control']=='no-store'
    status,data,_=get(url+'frame.png');assert status==204 and data==b''
    assert program.calls==before
    with pytest.raises(urllib.error.HTTPError) as caught:get(url+'keyboard',data=b'press a',method='POST')
    assert caught.value.code==405 and program.calls==before
    with pytest.raises(urllib.error.HTTPError) as caught:get(url+'frame.png',headers={'Origin':'https://unrelated.invalid'})
    assert caught.value.code==403 and program.calls==before


def test_dot_mode_renders_only_explicitly_retained_png_and_stops_with_session(program):
    url=program.dot_mode(True)['viewer_url'];capture=program.spectator_frame()
    before=list(program.calls);status,data,_=get(url+'frame.png')
    assert status==200 and data.startswith(b'\x89PNG\r\n\x1a\n')
    assert program.calls==before
    status,metadata,_=get(url+'state.json');assert status==200 and str(capture['metadata']['frame_id']).encode() in metadata
    program._windows_ui_close()
    assert program.dot_mode()['enabled'] is False
    with pytest.raises((urllib.error.URLError,TimeoutError)):get(url)


def test_dot_mode_capability_url_and_exact_host_are_required(program):
    url=program.dot_mode(True)['viewer_url']
    with pytest.raises(urllib.error.HTTPError) as caught:get(url.replace(url.split('/')[-2],'wrong-token'))
    assert caught.value.code==404
    with pytest.raises(urllib.error.HTTPError) as caught:get(url,headers={'Host':'different.invalid'})
    assert caught.value.code==403
    assert not program.calls


def test_automatic_spectator_updates_replace_one_buffer_without_growing_persistent_artifacts(program):
    url=program.dot_mode(True)['viewer_url']
    before=program.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    program._windows_refresh_spectator()
    status,first,_=get(url+'frame.png');assert status==200
    program.rgb=(200,100,50);program._windows_refresh_spectator()
    status,second,_=get(url+'frame.png');assert status==200 and second!=first
    after=program.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    assert before==after==0
    assert program.dot_mode()['frame']['retention'].startswith('latest owned spectator buffer')
