"""Shared bounded integer validation for CHimpREC helpers."""

_MAX_SLOTS = 1_000_000


def _unsigned(value, bits, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must be an unsigned {bits}-bit integer")
    return value
