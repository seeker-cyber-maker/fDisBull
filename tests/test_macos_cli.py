"""Public macOS probes stay bound to the imported original source."""
from fdisbull.cli import parser, respond
from fdisbull.project import Project
from fixtures_formats import macho_arm64


def _project(tmp_path):
    source = tmp_path / 'authored-arm64'
    source.write_bytes(macho_arm64())
    project = tmp_path / 'authored.fdb'
    with Project.create(project, source):
        pass
    return source, project


def test_macos_probe_commands_parse_named_inputs():
    args = vars(parser().parse_args([
        'ghidra-arm64', 'study.fdb', 'app', '--address', '0x100000100',
        '--analyze-headless', '/tool/analyzeHeadless', '--decompile-entry', '0x100000100',
    ]))
    assert args['addresses'] == [0x100000100]
    assert args['decompile_entry'] == 0x100000100
    args = vars(parser().parse_args([
        'macos-observe', 'study.fdb', 'app', '--symbol', 'main', '--arg', 'one',
    ]))
    assert args['argv'] == ['one']


def test_ghidra_probe_checks_project_source_before_external_tool(tmp_path, monkeypatch):
    source, project = _project(tmp_path)
    from fdisbull import ghidra_arm64

    calls = []
    def probe(path, addresses, **options):
        calls.append((path, addresses, options))
        from hashlib import sha256
        return {'format': 'fdisbull-ghidra-arm64-facts-1', 'status': 'complete',
                'source_sha256': sha256(path.read_bytes()).hexdigest()}
    monkeypatch.setattr(ghidra_arm64, 'probe_macho_arm64', probe)
    params = {'project': str(project), 'path': str(source), 'addresses': [0x100000100],
              'analyze_headless': '/tool/analyzeHeadless'}
    good = respond({'method': 'ghidra-arm64', 'params': params})
    assert good['ok'] and good['result']['fdisbull_project']['version'] == 1
    assert len(calls) == 1

    wrong = tmp_path / 'changed-arm64'
    changed = bytearray(source.read_bytes())
    changed[0x100] ^= 1
    wrong.write_bytes(changed)
    bad = respond({'method': 'ghidra-arm64', 'params': dict(params, path=str(wrong))})
    assert not bad['ok'] and 'source hash' in bad['error']['message']
    assert len(calls) == 1
    def changed_during_probe(path, addresses, **options):
        return {'format': 'fdisbull-ghidra-arm64-facts-1', 'source_sha256': '0' * 64}
    monkeypatch.setattr(ghidra_arm64, 'probe_macho_arm64', changed_during_probe)
    raced = respond({'method': 'ghidra-arm64', 'params': params})
    assert not raced['ok'] and 'source changed' in raced['error']['message']


def test_lldb_probe_checks_project_source_before_launch(tmp_path, monkeypatch):
    source, project = _project(tmp_path)
    from fdisbull import macos_lldb

    calls = []
    def observe(path, **options):
        calls.append((path, options))
        from hashlib import sha256
        return {'schema': 'fdisbull-macos-lldb-observation-1', 'status': 'ok',
                'source': {'sha256': sha256(path.read_bytes()).hexdigest()}}
    monkeypatch.setattr(macos_lldb, 'observe_macos_arm64_launch', observe)
    params = {'project': str(project), 'executable': str(source), 'symbol': 'main'}
    good = respond({'method': 'macos-observe', 'params': params})
    assert good['ok'] and good['result']['fdisbull_project']['source_sha256']
    assert len(calls) == 1
    bad = respond({'method': 'macos-observe', 'params': dict(params, version=2)})
    assert not bad['ok'] and 'original byte version' in bad['error']['message']
    assert len(calls) == 1
