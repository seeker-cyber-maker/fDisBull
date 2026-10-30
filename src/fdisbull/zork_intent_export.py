"""Private exports for partial game-intent recovery and its source definitions."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .zork_intents import recover_intents, verify_bindings
from .zork_uil import _private_destination, write_document


def export_intents(story, *, output, ir=None, uil=None, udl=None):
    """Preserve a supplied executable IR and export the separate intent layer.

    All destinations are checked before recovery or writing. The optional
    standalone UIL/UDL files are the exact documents embedded in the runnable
    package, not independently generated approximations.
    """
    targets = [Path(path).expanduser().resolve() for path in (output, uil, udl) if path]
    if len(set(targets)) != len(targets):
        raise ValueError("Output paths must be distinct")
    inputs = {Path(path).expanduser().resolve() for path in (story, ir) if path}
    if inputs.intersection(targets):
        raise ValueError("Outputs must not replace the story or retained IR")
    for path in targets:
        _private_destination(path)
    program = None
    if ir:
        path = Path(ir).expanduser()
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Retained IR exceeds its input budget")
        program = json.loads(raw)
    package = recover_intents(story, low_level_ir=program)
    receipt = verify_bindings(package)
    outputs = {"package": write_document(output, package)}
    for name, destination in (("uil", uil), ("udl", udl)):
        if destination:
            outputs[name] = write_document(destination, package[name])
    return {"source": package["udl"]["source"], "bindings": receipt,
            "qualification": package["udl"]["qualification"], "outputs": outputs}
