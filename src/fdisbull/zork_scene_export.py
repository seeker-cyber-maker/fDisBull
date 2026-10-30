"""Private exports of recovered Zork scenes and their separate UDL definitions."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .zork_scenes import recover_scenes, verify_bindings
from .zork_uil import _private_destination, write_document


def export_scenes(story, *, output, intents=None, uil=None, udl=None, dispatch=None):
    """Check every destination before building or writing game-derived data."""
    targets = [Path(path).expanduser().resolve() for path in (output, uil, udl, dispatch) if path]
    if len(set(targets)) != len(targets):
        raise ValueError("Scene export paths must be distinct")
    inputs = {Path(path).expanduser().resolve() for path in (story, intents) if path}
    if inputs.intersection(targets):
        raise ValueError("Scene outputs must not replace the story or existing conversion")
    for path in targets:
        _private_destination(path)
    base = None
    if intents:
        path = Path(intents).expanduser()
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as stream:
            raw = stream.read(80 * 1024 * 1024 + 1)
        if len(raw) > 80 * 1024 * 1024:
            raise ValueError("Preserved intent package exceeds its input budget")
        base = json.loads(raw)
    package = recover_scenes(story, base_intents=base)
    receipt = verify_bindings(package)
    outputs = {"package": write_document(output, package)}
    for key, destination in (("uil", uil), ("udl", udl), ("dispatch_uil", dispatch)):
        if destination:
            outputs[key] = write_document(destination, package[key])
    return {"source": package["udl"]["source"], "bindings": receipt,
            "qualification": package["udl"]["qualification"], "outputs": outputs}
