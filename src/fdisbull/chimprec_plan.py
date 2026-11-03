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
        raise ValueError("import planning requires 32 or 64 bits")
    width = bits // 8
    entries = recovery.get("entries") if isinstance(recovery, dict) else recovery
    if not isinstance(entries, list):
        raise ValueError("recovery must contain an entries list")
    cuts_set = _address_set(cuts, "cuts")
    separators = _address_set(separators_before, "separators")
    override_map = {}
    for item in overrides or []:
        if not isinstance(item, dict):
            raise ValueError("import overrides must be dictionaries")
        address = _unsigned(item.get("address"), 64, "override address")
        if address in override_map:
            raise ValueError("duplicate import override")
        module, name, ordinal = item.get("module"), item.get("name"), item.get("ordinal")
        if not isinstance(module, str) or not module or len(module) > 4096:
            raise ValueError("override module must be a nonempty string")
        if (name is None) == (ordinal is None):
            raise ValueError("override needs exactly one of name or ordinal")
        if name is not None and (not isinstance(name, str) or not name or len(name) > 65536):
            raise ValueError("override name must be a nonempty string")
        if ordinal is not None:
            _unsigned(ordinal, 16, "override ordinal")
        override_map[address] = {"module": module, "name": name, "ordinal": ordinal,
                                 "forwarder": item.get("forwarder"), "selected_by": "manual_override"}

    selected = []
    seen = set()
    unresolved = []
    for raw in sorted(entries, key=lambda row: row.get("address", -1)):
        if not isinstance(raw, dict):
            raise ValueError("recovery entries must be dictionaries")
        address = _unsigned(raw.get("address"), 64, "import slot address")
        if address % width:
            raise ValueError("import slot address is not pointer-aligned")
        if address in seen:
            raise ValueError("duplicate import slot address")
        seen.add(address)
        if address in cuts_set:
            continue
        chosen = override_map.pop(address, None)
        if chosen is None:
            alternatives = raw.get("alternatives", [])
            if raw.get("status") == "padding" or raw.get("target") == 0:
                continue
            if not isinstance(alternatives, list):
                raise ValueError("entry alternatives must be a list")
            if len(alternatives) == 1:
                alt = alternatives[0]
                # An export can have both a name and an ordinal.  Import by
                # name when one is known; ordinal-only recovery remains
                # explicit and does not invent a symbol.
                chosen = {"module": alt.get("module"),
                          "name": alt.get("name"),
                          "ordinal": None if alt.get("name") is not None else alt.get("ordinal"),
                          "export_ordinal": alt.get("ordinal"),
                          "forwarder": alt.get("forwarder"),
                          "selected_by": "unique_runtime_export"}
            elif len(alternatives) > 1:
                unresolved.append({"address": address, "reason": "ambiguous_alias", "alternatives": alternatives})
                continue
            else:
                unresolved.append({"address": address, "reason": "unresolved_nonzero", "target": raw.get("target")})
                continue
        selected.append({"address": address, **chosen})
    if override_map:
        missing = ", ".join(hex(address) for address in sorted(override_map))
        raise ValueError("override addresses are absent from recovery entries: " + missing)
    if strict and unresolved:
        raise ValueError("unresolved or ambiguous import entries require a manual override or cut")

    descriptors = []
    current = None
    for item in selected:
        module = item["module"]
        if not isinstance(module, str) or not module:
            raise ValueError("selected import lacks module")
        if (item.get("name") is None) == (item.get("ordinal") is None):
            raise ValueError("selected import needs exactly one of name or ordinal")
        if item.get("ordinal") is not None:
            _unsigned(item["ordinal"], 16, "import ordinal")
        if (current is None or item["address"] in separators
                or current["module"].casefold() != module.casefold()
                or item["address"] != current["entries"][-1]["address"] + width):
            current = {"module": module, "entries": []}
            descriptors.append(current)
        current["entries"].append(item)
    return {"format": "chimprec-import-plan-1", "bits": bits,
            "pointer_width": width, "descriptors": descriptors,
            "selected_count": len(selected), "unresolved": unresolved,
            "manual_cuts": sorted(cuts_set), "manual_separators": sorted(separators),
            "complete": not unresolved}
