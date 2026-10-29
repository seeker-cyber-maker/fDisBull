from fdisbull import player_checkpoints
from fdisbull.text_host import _config
from test_player_checkpoints import Project, Session, Handle
import pytest


def test_checkpoint_restore_preserves_session_policy(tmp_path):
    p=Project(tmp_path/'checkpoint.sqlite'); s=Session(p); h=Handle(s)
    s._allow_assisted_travel=True
    assert player_checkpoints.save(h)['complete']
    s._allow_assisted_travel=False
    assert player_checkpoints.load(h)['status']=='restored'
    assert s._allow_assisted_travel is False


def test_host_policy_is_strict_boolean():
    cfg={'format':'fdisbull-text-host-1','project':'p','backend':'b','game_dir':'g','projection':'p'}
    assert _config(cfg)==(0,60000)
    assert _config(dict(cfg,fair_play=True))==(0,60000)
    with pytest.raises(ValueError): _config(dict(cfg,fair_play='true'))
