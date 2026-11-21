"""Owned adapter for native cycle controls and a stopped draw request.

The profile has no draw-completion or actor-state injection API. A pending
request remains architectural state even when observations are disabled.
"""
from copy import deepcopy

from harness import HarnessError
from visual_binding_harness import QemuAGIViewBinding


DRAW_INTENT_PROFILE = "agi-2917-draw-intent-pilot-1"
STATE_SCHEMA = "fdisbull-agi-intent-state-1"
EVENTS_SCHEMA = "fdisbull-agi-intent-events-1"


def intent_guest_state(state):
    """Copy every architectural field, including a pending effect if present."""
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA \
            or not isinstance(state.get("guest"), dict):
        raise HarnessError("Unsupported AGI draw-intent state schema")
    return deepcopy(state["guest"])


class QemuAGIDrawIntent(QemuAGIViewBinding):
    """Select the explicit startup-only profile using the existing QMP owner."""

    profile = DRAW_INTENT_PROFILE
    state_schema = STATE_SCHEMA
    events_schema = EVENTS_SCHEMA
    machine_properties = ("draw-intent=on",)
