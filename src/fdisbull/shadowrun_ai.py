"""Repeatable entry points for the source-bound Pac-Man-like actor stage."""
from .shadowrun_combat import ROM_SHA256


def profiles():
    return {
        'format': 'fdisbull-shadowrun-ai-profiles-1',
        'stage': 'pacman-like',
        'source_rom_sha256': ROM_SHA256,
        'profiles': [{
            'id': 'assisted-arena',
            'default_preset': 'stationary',
            'presets': {
                'stationary': 'Source-constructed armed actor in prepared scene 2',
                'moving': 'Same source actor with explicit initial cooldown 2 for movement',
            },
            'default_target': 'nes',
            'targets': {
                'nes': 'Preserved MMC3 research output; possible but not recommended for Genesis-class games',
                'macos-arm64': 'Native local application from the same Genesis-bound procedural UIL',
            },
            'requires': ['reviewed opening manifest', 'exact source ROM',
                         'receipt-bound scene-2 frame-5999 capture'],
            'target_requires': {'nes': ['cc65 toolchain'],
                                'macos-arm64': ['macOS ARM64', 'Clang and macOS SDK']},
            'output': 'private target artifact and build receipts',
            'model_entry': 'shadowrun_arena_frame',
            'limits': ['assisted source-constructed encounter, not natural scene progression',
                       'bounded actor, equipment, terrain and concurrency paths',
                       'symbolic presentation; original graphics/audio not reproduced',
                       'unsupported continuations refuse; no full-game or hardware parity'],
        }],
    }


def build(path, *, rom_path, capture, output, cc65_root=None,
          profile='assisted-arena', preset='stationary', target='nes'):
    if profile != 'assisted-arena' or preset not in ('stationary', 'moving'):
        raise ValueError('unsupported Shadowrun AI profile or preset')
    if target not in ('nes', 'macos-arm64'):
        raise ValueError('unsupported Shadowrun AI target')
    if target == 'macos-arm64':
        if cc65_root is not None:
            raise ValueError('--cc65-root applies to the NES target')
        from .shadowrun_macos import build_macos_assisted_arena
        result = build_macos_assisted_arena(path, rom_path=rom_path, capture=capture,
                                          output=output, preset=preset)
        return {**result, 'stage': 'pacman-like', 'profile': profile,
                'preset': preset, 'target': target}
    if cc65_root is None:
        raise ValueError('the NES target requires --cc65-root')
    from .shadowrun_nes_banked import build_banked_assisted_arena
    result = build_banked_assisted_arena(path, rom_path=rom_path, capture=capture,
        cc65_root=cc65_root, output=output, moving=(preset == 'moving'))
    return {**result, 'stage': 'pacman-like', 'profile': profile,
            'preset': preset, 'target': target}
