"""Complete pinned-source interface checks; no native build or execution."""
import json
from pathlib import Path
import shutil

import pytest

from scripts.dosbox_rpc_census import census, replay_member, server_methods


ROOT = Path(__file__).resolve().parents[1]
SOURCE = b'''static bool IsKnownMethod(const std::string& method)
{
    return method == "session.status";
}
void dispatch() {
    if (!IsKnownMethod(parsed.method))
        return unknown_method();
    if (parsed.method == "session.status") { status(); }
}
'''


def test_complete_source_includes_unchanged_upstream_diagnostics():
    result = census(ROOT)
    upstream = (ROOT / 'experimental/dosbox-x/census/agent_server.upstream.cpp').read_text()
    assert len(result['profiles']['stable']['methods']) == 36
    assert len(result['profiles']['layers']['methods']) == 37
    assert set(result['profiles']['layers']['methods']) - set(result['profiles']['stable']['methods']) == {'layers.configure'}
    for name in ('debug.output.read', 'debugger.execute_command'):
        assert name in upstream
        for profile in ('stable', 'layers'):
            # A future inspected patch may edit these handlers. The permanent
            # invariant is complete-source coverage, not absence from a diff.
            assert name in result['profiles'][profile]['methods']
            assert result['profiles'][profile]['exact_dispatch_lines'][name]
    for profile in result['profiles'].values():
        assert set(profile['methods']) == set(profile['exact_dispatch_lines']) | set(profile['reviewed_prefix_fallbacks'])
        assert set(profile['reviewed_prefix_fallbacks']) == {'input.mouse.state'}
        assert profile['unclassified_dispatch_uses'] == 0
    assert result['runtime_validation'] == 'not_run'


@pytest.mark.parametrize('before,after,error', [
    (b'method == "session.status";', b'method == "session.status" || method == "new_family.new_method";', 'lack reviewed dispatch'),
    (b'if (parsed.method == "session.status")', b'if (parsed.method == "new_family.new_method")', 'undeclared RPC'),
    (b'if (parsed.method == "session.status")', b'if (parsed.method != "session.status")', 'lack reviewed dispatch'),
    (b'return method == "session.status";', b'return true;', 'filter grammar'),
    (b'return method == "session.status";', b'return method == "session.status" || method == "session.status";', 'Duplicate known'),
    (b'if (!IsKnownMethod(parsed.method))\n        return unknown_method();', b'', 'leading rejecting'),
    (b'if (parsed.method == "session.status")', b'if (parsed.method.starts_with("session."))', 'Unclassified parsed.method'),
    (b'static bool IsKnownMethod', b'static bool OtherFilter', 'one complete IsKnownMethod'),
])
def test_missing_extra_or_unclassified_dispatch_cannot_pass(before, after, error):
    assert server_methods(SOURCE, {})['methods'] == ['session.status']
    with pytest.raises(ValueError, match=error):
        server_methods(SOURCE.replace(before, after), {})


def test_literals_in_comments_or_diagnostic_strings_are_not_routes():
    source = SOURCE + b'// parsed.method == "not.a_route"\nconst char* text = "parsed.method == \\"not.a_route\\"";\n'
    assert server_methods(source, {})['methods'] == ['session.status']


def test_prefix_fallback_requires_explicit_declared_method_and_statement():
    source = SOURCE.replace(b'session.status', b'input.mouse.state').replace(
        b'if (parsed.method == "input.mouse.state") { status(); }',
        b'if (parsed.method.compare(0,12,"input.mouse.")==0) { get_state(); }')
    witness = {'input.mouse.state': {'prefix': 'input.mouse.', 'required_statement': 'get_state();'}}
    assert server_methods(source, witness)['methods'] == ['input.mouse.state']
    with pytest.raises(ValueError, match='fallback statement'):
        server_methods(source.replace(b'get_state();', b'other();'), witness)
    with pytest.raises(ValueError, match='lack reviewed dispatch'):
        server_methods(source, {})
    with pytest.raises(ValueError, match='lack reviewed dispatch'):
        server_methods(source.replace(b'method == "input.mouse.state";',
            b'method == "input.mouse.state" || method == "input.mouse.extra";'), witness)


def test_patch_replay_requires_exact_context_offsets_and_counts():
    patch = b'''diff --git a/src/agent/server/agent_server.cpp b/src/agent/server/agent_server.cpp
--- a/src/agent/server/agent_server.cpp
+++ b/src/agent/server/agent_server.cpp
@@ -1,2 +1,2 @@
 A
-B
+C
'''
    assert replay_member(b'A\nB\n', patch) == b'A\nC\n'
    with pytest.raises(ValueError, match='context differs'):
        replay_member(b'A\nchanged\n', patch)
    with pytest.raises(ValueError, match='offset differs'):
        replay_member(b'A\nB\n', patch.replace(b'+1,2', b'+2,2'))
    with pytest.raises(ValueError, match='counts differ'):
        replay_member(b'A\nB\n', patch.replace(b'-1,2', b'-1,3'))
    with pytest.raises(ValueError, match='one native server diff'):
        replay_member(b'A\nB\n', patch + patch)


@pytest.mark.parametrize('change,error', [
    ('upstream', 'Upstream native server identity'),
    ('patch', 'Native patch identity'),
    ('result', 'Reconstructed native server identity'),
    ('baseline', 'Native source baseline'),
])
def test_source_census_rejects_identity_drift(tmp_path, change, error):
    paths = ['experimental/dosbox-x/census/agent_server.upstream.cpp',
             'experimental/dosbox-x/census/upstream.json']
    for directory in ('experimental/dosbox-x', 'experimental/dosbox-x/layers'):
        paths.extend(directory + '/' + name for name in ('headless-agent.patch', 'source-manifest.json'))
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    stable = tmp_path / 'experimental/dosbox-x'
    if change == 'upstream':
        with (stable / 'census/agent_server.upstream.cpp').open('ab') as stream:
            stream.write(b'\n')
    elif change == 'patch':
        with (stable / 'headless-agent.patch').open('ab') as stream:
            stream.write(b'\n')
    else:
        path = stable / 'source-manifest.json'
        manifest = json.loads(path.read_text())
        if change == 'baseline':
            manifest['baseline_commit'] = '0' * 40
        else:
            next(x for x in manifest['source_files'] if x['path'] == 'src/agent/server/agent_server.cpp')['sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=error):
        census(tmp_path)
