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
            'requires': ['reviewed opening manifest', 'exact source ROM',
                         'receipt-bound scene-2 frame-5999 capture', 'cc65 toolchain'],
            'output': 'private MMC3 NES cartridge and build receipts',
            'model_entry': 'shadowrun_arena_frame',
            'limits': ['assisted source-constructed encounter, not natural scene progression',
                       'bounded actor, equipment, terrain and concurrency paths',
                       'symbolic presentation; original graphics/audio not reproduced',
                       'unsupported continuations refuse; no full-game or hardware parity'],
        }],
    }


def build(path, *, rom_path, capture, cc65_root, output,
          profile='assisted-arena', preset='stationary'):
    if profile != 'assisted-arena' or preset not in ('stationary', 'moving'):
        raise ValueError('unsupported Shadowrun AI profile or preset')
    from .shadowrun_nes_banked import build_banked_assisted_arena
    result = build_banked_assisted_arena(path, rom_path=rom_path, capture=capture,
        cc65_root=cc65_root, output=output, moving=(preset == 'moving'))
    return {**result, 'stage': 'pacman-like', 'profile': profile, 'preset': preset}
