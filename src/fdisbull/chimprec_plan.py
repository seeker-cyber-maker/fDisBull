"""Reviewed CHimpREC import-plan construction.

The recovery scanner deliberately keeps aliases and unresolved cells.  This
module turns an analyst-reviewed selection into the deterministic descriptor
plan consumed by :mod:`fdisbull.chimprec_pe`.
"""
from __future__ import annotations

from .chimprec_common import _MAX_SLOTS, _unsigned

def _address_set(values, label):
    if values is None:
        return set()
    if not isinstance(values, list) or len(values) > _MAX_SLOTS:
        raise ValueError(f"{label} must be a list")
    result = set()
    for value in values:
        _unsigned(value, 64, label[:-1] if label.endswith('s') else label)
        if value in result:
            raise ValueError(f"duplicate {label[:-1] if label.endswith('s') else label}")
        result.add(value)
    return result


def build_import_plan(recovery: dict | list[dict], bits: int, *,
                      overrides: list[dict] | None = None,
                      cuts: list[int] | None = None,
                      separators_before: list[int] | None = None,
                      strict: bool = True) -> dict:
    """Turn reviewed recovery entries into explicit import descriptors.

    This is the scriptable equivalent of CHimpREC's import editing, ``Show
    Invalid``, ``Cut thunk(s)``, ordinal selection and manual module separation.
    It never guesses among aliases. ``overrides`` may select or replace one slot
    using ``address``, ``module`` and exactly one of ``name``/``ordinal``.
    ``cuts`` explicitly discard junk cells. ``separators_before`` force a new
    descriptor before a slot even when the module and addresses are contiguous.

    With ``strict=True`` every unresolved nonzero entry must be cut or manually
    resolved, and every ambiguous entry must be overridden.  Zero padding is
    ignored. The output is a deterministic descriptor plan consumed by the PE
    writer; it does not modify captured memory.
    """
    if bits not in (32, 64):
        raise ValueError&ˆ