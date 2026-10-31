"""Build the bounded Civ city BUY commit as a UDC module.

Recovered from the DOS listing of the city screen at R:0D12:4C00 (cost) and
R:0D12:4DD6 (commit), via the Civ64 route map (R:0D12:xxxx -> fDisBull runtime
1D12:xxxx):

    4c00  mov bx,[0x6548] / shl bx,1 / mov ax,[bx-0x4e2a]  ; civ gold table
    ...   cost = item_cost * [bp-0x4a] - word [si+0x70fa]   ; minus shield stock
    4de2  add word [bx+0x70fa], ax                          ; shields += cost
    4df2  shl ax,1 / sub word [bx-0x4e2a], ax               ; gold -= 2 * cost
    4dfe  and byte [bx+0x70f2], 0xef                        ; clear the buy flag

The item-cost derivation (table lookup times an unknown multiplier) stays
outside the model; a caller supplies the computed remaining-shield cost.  The
status bit clear is a UI flag and is also outside this bounded transition.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

from examples.civ.civ_city_uil import EXPECTED_UNPACKED_SHA256, _sha256
from fdisbull.interaction_il import validate_il
from fdisbull.project import Project
from fdisbull.udc_layers import (
    build_selection_shell,
    register_contract,
    register_layer,
    select_layers,
)

COST_SITE = "1D12:4C00"
COMMIT_SITE = "1D12:4DD6"
COST_SNIPPET_SIZE = 0x40
COMMIT_SNIPPET_SIZE = 0x30


def buy_program(initial: dict | None = None) -> dict:
    values = {
        "$shield_box": {"type": "i16", "initial": 0},
        "$treasury": {"type": "u16", "initial": 0},
        "$remaining": {"type": "i16", "initial": 0},
        "$gold_cost": {"type": "i16", "initial": 0},
    }
    if initial is not None:
        if not isinstance(initial, dict) or set(initial) - set(values):
            raise ValueError("initial state contains an unknown Civ buy variable")
        for name, value in initial.items():
            values[name]["initial"] = value
    program = {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": values,
        "resources": {},
        "body": [
            {
                "id": "copy-cost",
                "op": "set",
                "var": "$gold_cost",
                "value": {"var": "$remaining"},
            },
            {
                "id": "double-cost",
                "op": "add",
                "var": "$gold_cost",
                "value": {"var": "$remaining"},
            },
            {
                "id": "add-shields",
                "op": "add",
                "var": "$shield_box",
                "value": {"var": "$remaining"},
            },
            {
                "id": "debit-gold",
                "op": "subtract",
                "var": "$treasury",
                "value": {"var": "$gold_cost"},
            },
        ],
    }
    validate_il(program)
    return program


def _contract(program: dict, evidence: dict) -> dict:
    return {
        "format": "fdisbull-block-contract-1",
        "name": "civ.city.buy.commit",
        "author": "civ-city-buy-slice",
        "inputs": {"shield_box": "i16", "treasury": "u16", "remaining": "i16"},
        "outputs": {"shield_box": "i16", "treasury": "u16"},
        "behavior": {"kind": "uil", "program": deepcopy(program)},
        "domain": {},
        "evidence": {
            "source": evidence,
            "boundary": {
                "cost": "remaining = item_cost * multiplier - shield_box, computed by the caller; the multiplier at [bp-0x4a] is not recovered.",
                "commit": "shields += remaining, gold -= 2 * remaining, with 16-bit wraparound as in the source.",
                "excluded": "The item-cost table lookup and the status flag clear (and byte [bx+0x70f2], 0xef) are outside this transition.",
            },
        },
    }


PUBLIC = ("$shield_box", "$treasury", "$remaining")


def _public_state(primitive: dict) -> dict:
    return {
        name: deepcopy(value)
        for name, value in primitive["variables"].items()
        if name in PUBLIC
    }


def _module_program(contract_id: str, primitive: dict) -> dict:
    return {
        "format": "fdisbull-module-uil-1",
        "role": "uil",
        "variables": _public_state(primitive),
        "resources": {},
        "body": [
            {
                "id": "invoke-city-buy",
                "op": "invoke",
                "binding": "city-buy",
                "contract": contract_id,
                "inputs": {
                    "shield_box": {"var": "$shield_box"},
                    "treasury": {"var": "$treasury"},
                    "remaining": {"var": "$remaining"},
                },
                "outputs": {
                    "shield_box": "$shield_box",
                    "treasury": "$treasury",
                },
            }
        ],
    }


def build_buy_udc(
    source: str | Path,
    destination: str | Path,
    *,
    project_path: str | Path | None = None,
    initial: dict | None = None,
    target: str = "linux-x64",
) -> dict:
    """Build a source-bound UDC shell for the recovered BUY commit."""
    source_path = Path(source).expanduser().resolve(strict=True)
    source_sha256 = _sha256(source_path)
    if source_sha256 != EXPECTED_UNPACKED_SHA256:
        raise ValueError(
            "Civ buy UDC requires the pinned unpacked root "
            f"{EXPECTED_UNPACKED_SHA256}; got {source_sha256}"
        )
    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists():
        raise ValueError("UDC destination must be new")
    if project_path is None:
        project_path = destination_path.with_name(destination_path.name + ".fdb")
    project_path = Path(project_path).expanduser().resolve()
    if project_path.exists():
        raise ValueError("UDC project path must be new")

    evidence = {
        "original_root": {
            "sha256": source_sha256,
            "bytes": source_path.stat().st_size,
            "file": source_path.name,
        },
        "disassembly": {
            "route": "R:0D12:4C00 cost, R:0D12:4DD6 commit -> runtime 1D12 same offsets",
            "shields": "add word [bx+0x70fa], ax",
            "gold": "shl ax,1; sub word [bx-0x4e2a], ax",
            "flag": "and byte [bx+0x70f2], 0xef",
            "unrecovered": "the multiplier at [bp-0x4a] and the item-cost tables",
        },
        "civ64_docs": {
            "repository": "Buyukcaglar/Civ64",
            "paths": ["docs/dos/SCENES-PLAY.md 7.1", "docs/dos/OFFSETS.md"],
            "role": "crosswalk for the buy box and the city record offsets",
        },
    }
    primitive = buy_program(initial)
    contract = _contract(primitive, evidence)

    with Project.create(project_path, source_path) as project:
        cost = project.capture_snippet(
            "civ-city-buy-cost",
            [{"address": COST_SITE, "size": COST_SNIPPET_SIZE}],
            evidence={
                "site": COST_SITE,
                "role": "cost = item_cost * multiplier - shield_box",
            },
            boundary="cost derivation window; tables and multiplier unresolved",
            author="civ-city-buy-slice",
        )
        commit = project.capture_snippet(
            "civ-city-buy-commit",
            [{"address": COMMIT_SITE, "size": COMMIT_SNIPPET_SIZE}],
            evidence={
                "site": COMMIT_SITE,
                "role": "shields += cost; gold -= 2 * cost; clear flag",
            },
            boundary="commit stores only",
            author="civ-city-buy-slice",
        )
        contract_record = register_contract(
            project, contract, author="civ-city-buy-slice"
        )
        contract_id = contract_record["id"]
        layer = {
            "format": "fdisbull-udl-layer-1",
            "name": "civ-city-buy-commit-uil",
            "author": "civ-city-buy-slice",
            "contract": contract_id,
            "snippet": commit["id"],
            "implementation": {"backend": "uil", "program": deepcopy(primitive)},
            "assurance": {
                "kind": "candidate-source-bound-model",
                "source_to_uil": "commit stores proven by disassembly; cost derivation not modelled",
            },
            "evidence": {"cost_snippet": cost["id"], "commit_snippet": commit["id"]},
        }
        layer_record = register_layer(project, layer, author="civ-city-buy-slice")
        module = _module_program(contract_id, primitive)
        selection_record = select_layers(
            project,
            "civ-city-buy-selection",
            {"city-buy": layer_record["id"]},
            program=module,
            target=target,
            author="civ-city-buy-slice",
        )
        plan = {
            "format": "fdisbull-native-shell-1",
            "entry": "main",
            "state": _public_state(primitive),
            "resources": {},
            "functions": {"main": {"body": [{"op": "call", "binding": "city-buy"}]}},
            "evidence": {"source": evidence, "commit_snippet": commit["id"]},
        }
        build = build_selection_shell(
            project,
            selection_record["id"],
            plan,
            destination_path,
            target=target,
            capture_state=(target != "macos-arm64"),
        )
        return {
            "format": "fdisbull-civ-city-buy-udc-build-1",
            "source": evidence["original_root"],
            "snippets": {
                "cost": {"id": cost["id"], "sha256": cost["sha256"], "site": COST_SITE},
                "commit": {
                    "id": commit["id"],
                    "sha256": commit["sha256"],
                    "site": COMMIT_SITE,
                },
            },
            "contract": {
                "id": contract_id,
                "sha256": contract_record["sha256"],
                "name": contract["name"],
            },
            "selection": {
                "id": selection_record["id"],
                "sha256": selection_record["sha256"],
            },
            "native_build": build,
            "qualification": build["qualification"],
            "scope": "bounded buy commit; cost derivation and status flag excluded",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the bounded Civ city BUY UDC module"
    )
    parser.add_argument("source", help="exact generated CIV_UNP.EXE")
    parser.add_argument("destination", help="new output directory outside Git")
    parser.add_argument("--project", help="new private fDisBull project path")
    parser.add_argument("--state", help="JSON object overriding initial module state")
    parser.add_argument(
        "--target", choices=("linux-x64", "macos-arm64"), default="linux-x64"
    )
    args = parser.parse_args(argv)
    try:
        initial = None
        if args.state:
            with Path(args.state).open("rb") as stream:
                initial = json.load(stream)
        receipt = build_buy_udc(
            args.source,
            args.destination,
            project_path=args.project,
            initial=initial,
            target=args.target,
        )
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        print(
            json.dumps(
                {
                    "format": "fdisbull-civ-city-buy-udc-build-1",
                    "status": "refused",
                    "error": str(exc),
                }
            )
        )
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
