import pytest
from test_qemu_screenshot_hooks import capture_owner, policy, com_project
from fdisbull.screenshot_hooks import ScreenshotHookError


def test_late_final_event_cannot_return_success(capture_owner,monkeypatch):
    o=capture_owner;o.session.screenshot_hooks(policy())
    now=[100.0];monkeypatch.setattr('time.monotonic',lambda:now[0])
    o.session._rpc_deadline=100.5
    original=o.session._event
    def late(name,data):
        result=original(name,data)
        if name=='screenshot-hooks':now[0]=101.0
        return result
    o.session._event=late
    with pytest.raises((TimeoutError,ScreenshotHookError)) as failed:o.session.screenshot()
    result=failed.value.result
    assert result['capture']['artifact'] and result['restore']['ok']
    assert result['ok'] is False
    assert not o.session.closed


@pytest.mark.parametrize('operation',['configure','capture'])
def test_closed_owner_admission_is_explicit(capture_owner,operation):
    o=capture_owner;o.project.debug_screenshot_hooks(policy())
    o.session.closed=True;o.session.vm=None
    with pytest.raises(ValueError,match='owner|machine|live'):
        if operation=='configure':o.session.screenshot_hooks(policy())
        else:o.session.screenshot()
