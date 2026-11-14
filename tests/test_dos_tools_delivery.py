"""Installed-surface declarations and authored CLI behavior."""
import json
from pathlib import Path
import tomllib

from fdisbull.dos_tools import main
from test_rtlink import authored

ROOT=Path(__file__).resolve().parents[1]


def test_console_entry_and_indexed_skill_are_packaged():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert project['project']['scripts']['fdisbull-dos']=='fdisbull.dos_tools:main'
    from fdisbull.cli import AGENT_SKILLS
    # The existing reference stays indexed; no invisible companion skill.
    assert 'references/formats-and-media.md' in AGENT_SKILLS['fdisbull-investigate']['guides']
    reference=(ROOT/'src/fdisbull/skills/fdisbull-investigate/references/formats-and-media.md').read_text()
    for text in ('e_lfanew','PSP','RTLink','--argument=-p','GAME.INS','not a runnable EXE','protected-mode selector'):
        assert text in reference


def test_additive_methods_and_disassembly_cli(tmp_path,capsys):
    assert main(['methods'])==0
    methods=json.loads(capsys.readouterr().out)
    assert 'rtlink-inspect' in methods['result']['commands']
    target=tmp_path/'authored.exe';target.write_bytes(authored())
    assert main(['rtlink-disasm',str(target),'--overlay','2','--count','1'])==0
    response=json.loads(capsys.readouterr().out)
    assert response['ok'] and response['result']['instructions'][0]['mnemonic']=='push'
    assert main(['rtlink-disasm',str(target),'--overlay','99'])==1
    assert not json.loads(capsys.readouterr().out)['ok']
