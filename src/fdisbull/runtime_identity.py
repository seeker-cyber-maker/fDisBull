"""One runtime/package identity source with no execution or import side effects.

The issue contract distinguishes the full candidate identity shown by the tool
(`0.34.1rc1`) from the primary version recorded in lasting analysis artifacts
(`0.34.1`). Distribution metadata stays PEP 440 normalized (`0.34.1rc1`) and the
displayed candidate form is exposed through :func:`identity` so the mapping is
explicit. A missing or mismatched RC component is an installation diagnostic,
never guessed.
"""

from __future__ import annotations

import re

from . import __version__

_RUNTIME_VERSION_RE = re.compile(
    r"^(?P<primary>\d+\.\d+\.\d+)"
    r"(?P<candidate>-?rc(?P<number>[0-9]+))?$"
)


def _metadata_version():
    try:
        import importlib.metadata

        return importlib.metadata.version("fdisbull")
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None


def _distribution_version():
    # Prefer the installed distribution record; fall back to the runtime
    # constant when the package is used from an unreleased source tree.
    version = _metadata_version()
    return version if version is not None else __version__


def release_version():
    """Primary (final) version line, e.g. ``0.34.1`` from ``0.34.1rc1``."""
    match = _RUNTIME_VERSION_RE.match(_distribution_version())
    if match is None:
        return None
    return match.group("primary")


def candidate_number():
    """Numeric ``N`` of ``-rcN``, or ``None`` for a final build."""
    match = _RUNTIME_VERSION_RE.match(_distribution_version())
    if match is None or match.group("number") is None:
        return None
    return int(match.group("number"))


def identity(**context):
    """Full candidate identity dictionary for tool-facing outputs.

    ``runtime_version`` and ``distribution_version`` report what is actually
    present; they are never rewritten. A normalized-metadata mismatch with the
    runtime constant is recorded, not silently repaired.
    """
    distribution_version = _distribution_version()
    metadata_version = _metadata_version()
    runtime_version = __version__
    primary = release_version()
    candidate = candidate_number()
    candidate_number_value = None
    if candidate is not None:
        candidate_number_value = candidate
    mismatch = None
    if metadata_version is not None and metadata_version != runtime_version:
        mismatch = "distribution_metadata_mismatch"
    return {
        "format": "fdisbull-runtime-identity-1",
        "runtime_version": runtime_version,
        "distribution_version": distribution_version,
        "primary_version": primary,
        "candidate_number": candidate_number_value,
        "candidate_label": (
            f"{primary}-rc{candidate_number_value}"
            if candidate_number_value is not None
            else None
        ),
        "distribution_metadata_version": metadata_version,
        "metadata_normalization": mismatch,
        "context": context or None,
        "identity_scope": "One build-version source; no build/release certification.",
    }
