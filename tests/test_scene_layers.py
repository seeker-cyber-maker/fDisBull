"""Layer-backend-only scene acceptance, separate from stable DOS tests."""
from test_scene_improvements import counter_game, test_relative_outcome_preserves_debugger_stops as _stops
from test_debugger import emulator


def test_relative_outcome_preserves_hook_stop(counter_game,emulator):
    _stops(counter_game,emulator,'hook')
