"""Compatibility import for the shared, non-writing memory-search kernel.

Live capture and artifact ownership remain in fdisbull.memory_search_runtime.
The shared implementation retains the existing fdisbull-* serialized formats.
"""
from fdisbull_core.memory_search import (
    MAX_CANDIDATES,
    MAX_INTERVALS,
    MAX_RESULT_ROWS,
    MAX_SNAPSHOT_BYTES,
    plan_edit,
    refine_search,
    search_results,
    snapshot_metadata,
    start_search,
    validate_search,
    validate_snapshot,
)

__all__ = [
    "MAX_CANDIDATES", "MAX_INTERVALS", "MAX_RESULT_ROWS", "MAX_SNAPSHOT_BYTES",
    "plan_edit", "refine_search", "search_results", "snapshot_metadata",
    "start_search", "validate_search", "validate_snapshot",
]
