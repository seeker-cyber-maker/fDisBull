"""Bounded foreground jobs retain results without exhausting a live server."""
import threading

import pytest

from fdisbull.debugger import DebugWorkspace


class Session:
    metadata={'backend':'scummvm-agi'};run_id='new'
    _run_condition=threading.Condition();_run_sent=True
    def run(self):return {'outcome':'budget'}
    def _event(self,*args):pass


def test_collected_completed_jobs_can_be_reclaimed_for_another_run():
    workspace=DebugWorkspace()
    for index in range(64):
        done=threading.Event();done.set()
        workspace.async_runs[str(index)]={'run':'old','done':done,'collected':True}
    result=workspace._start_async(Session(),{})
    final=workspace._async_result('new',result['operation'],wait_ms=1000)
    assert final['complete'] and final['result']['outcome']=='budget'
    assert len(workspace.async_runs)==64 and '0' not in workspace.async_runs


def test_thread_start_failure_leaves_no_pending_job(monkeypatch):
    workspace=DebugWorkspace()
    def refuse(self):raise RuntimeError('no worker available')
    monkeypatch.setattr(threading.Thread,'start',refuse)
    with pytest.raises(RuntimeError,match='no worker'):
        workspace._start_async(Session(),{})
    assert workspace.async_runs=={}


def test_stop_reclaims_completed_jobs():
    workspace=DebugWorkspace()
    result=workspace._start_async(Session(),{})
    workspace._async_result('new',result['operation'],wait_ms=1000)
    workspace._join_async('new')
    assert workspace.async_runs=={}
