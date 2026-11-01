"""Public profile refusal must precede private input/output access."""
import pytest

from fdisbull.shadowrun_ai import build, profiles


@pytest.mark.parametrize('profile,preset', [
    ('whole-game', 'stationary'), ('assisted-arena', 'unknown'),
])
def test_unknown_ai_contract_refuses_before_creating_output(tmp_path, profile, preset):
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='profile or preset'):
        build('nonexistent-manifest', rom_path='nonexistent-rom',
              capture='nonexistent-capture', cc65_root='nonexistent-toolchain',
              output=output, profile=profile, preset=preset)
    assert not output.exists()


def test_projectless_profile_discovery_preserves_assisted_scope():
    result = profiles()
    assert result['stage'] == 'pacman-like'
    arena = next(p for p in result['profiles'] if p['id'] == 'assisted-arena')
    assert set(arena['presets']) == {'stationary', 'moving'}
    assert 'assisted' in ' '.join(arena['limits'])
    assert arena['model_entry'] == 'shadowrun_arena_frame'


@pytest.mark.parametrize('options,reason', [
    ({'target': 'unknown'}, 'target'),
    ({'target': 'nes'}, 'requires --cc65-root'),
    ({'target': 'macos-arm64', 'cc65_root': 'irrelevant'}, 'applies to the NES'),
])
def test_invalid_target_options_refuse_before_output(tmp_path, options, reason):
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match=reason):
        build('nonexistent-manifest', rom_path='nonexistent-rom',
              capture='nonexistent-capture', output=output, **options)
    assert not output.exists()
