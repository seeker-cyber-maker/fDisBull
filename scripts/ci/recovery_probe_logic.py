"""Isolated source-repair canary; never a product readiness implementation.

The rehearsal starts with this deliberately incomplete predicate. Its actual
repair worker must make the truth-table check pass on a new source commit.
"""


def capture_ready(observation):
    return not observation.get('errors')
