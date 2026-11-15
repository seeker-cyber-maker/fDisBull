"""Build the recovered Civ city BUY path as a UDC module.

Recovered from the DOS listing of the city screen (route space R:0D12):

    cost lookup 0x7387          production >= 0: unit table word [0x1142 + 0x22*id]
                                production <  0: improvement word [0xBB2 - 0x1E*id]
                                both hold the shield cost divided by ten
    price       0x73CD          base = ClampInt(10*cost10 - shield_box, 0, 999)
    unit        0x73D9..0x73F3  price = 2*base + (base*base as i16) / 20
    building    0x7430..0x743A  price = 2*base
    0x7446      buildings only  price *= 2 when -production > 0x15
    0x7461      both            price *= 2 when shield_box == 0
    guard       0x75D2          if treasury < price -> no purchase (signed)
    commit      0x75E5          word [city + 0x70FA] = 10 * cost10
                0x7604          civ gold -= price
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

PRICE_SITE = "1D12:7387"
COMMIT_SITE = "1D12:75E5"
PRICE_SNIPPET_SIZE = 0xE9
COMMIT_SNIPPET_SIZE = 0x25

PUBLIC = ("$shield_box", "$treasury", "$item_cost", "$production")
SCRATCH = (
    "$t2",
    "$t4",
    "$t8",
    "$t10",
    "$base",
    "$square",
    "$quotient",
    "$price",
    "$neg_id",
    "$twice",
)


def buy_program(initial: dict | None = None) -> dict:
    values = {
        "$shield_box": {"type": "i16", "initial": 0},
        "$treasury": {"type": "i16", "initial": 0},
        "$item_cost": {"type": "i16", "initial": 0},
        "$production": {"type": "i16", "initial": 0},
        "$t2": {"type": "i16", "initial": 0},
        "$t4": {"type": "i16", "initial": 0},
        "$t8": {"type": "i16", "initial": 0},
        "$t10": {"type": "i16", "initial": 0},
        "$base": {"type": "i16", "initial": 0},
        "$square": {"type": "i16", "initial": 0},
        "$quotient": {"type": "i16", "initial": 0},
        "$price": {"type": "i16", "initial": 0},
        "$neg_id": {"type": "i16", "initial": 0},
        "$twice": {"type": "i16", "initial": 0},
    }
    if initial is not None:
        if not isinstance(initial, dict) or set(initial) - set(values):
            raise ValueError("initial state contains an unknown Civ buy variable")
        for name, value in initial.items():
            values[name]["initial"] = value
    body = [
        {"id": "cost-x2", "op": "add", "var": "$t2", "value": {"var": "$item_cost"}},
        {"id": "cost-x2b", "op": "add", "var": "$t2", "value": {"var": "$item_cost"}},
        {"id": "cost-x4", "op": "add", "var": "$t4", "value": {"var": "$t2"}},
        {"id": "cost-x4b", "op": "add", "var": "$t4", "value": {"var": "$t2"}},
        {"id": "cost-x8", "op": "add", "var": "$t8", "value": {"var": "$t4"}},
        {"id": "cost-x8b", "op": "add", "var": "$t8", "value": {"var": "$t4"}},
        {"id": "cost-x10", "op": "add", "var": "$t10", "value": {"var": "$t8"}},
        {"id": "cost-x10b", "op": "add", "var": "$t10", "value": {"var": "$t2"}},
        {"id": "base", "op": "set", "var": "$base", "value": {"var": "$t10"}},
        {
            "id": "base-minus-stock",
            "op": "subtract",
            "var": "$base",
            "value": {"var": "$shield_box"},
        },
        {
            "id": "clamp-low",
            "op": "if",
            "condition": {
                "op": "not",
                "condition": {"op": "ge", "left": {"var": "$base"}, "right": 0},
            },
            "then": [
                {"id": "clamp-low-store", "op": "set", "var": "$base", "value": 0}
            ],
            "else": [],
        },
        {
            "id": "clamp-high",
            "op": "if",
            "condition": {"op": "ge", "left": {"var": "$base"}, "right": 1000},
            "then": [
                {"id": "clamp-high-store", "op": "set", "var": "$base", "value": 999}
            ],
            "else": [],
        },
        {"id": "square-load", "op": "set", "var": "$square", "value": {"var": "$base"}},
        {"id": "square", "op": "multiply", "var": "$square", "value": {"var": "$base"}},
        {
            "id": "quotient-load",
            "op": "set",
            "var": "$quotient",
            "value": {"var": "$square"},
        },
        {"id": "divide-20", "op": "divide", "var": "$quotient", "value": 20},
        {"id": "twice-base", "op": "set", "var": "$twice", "value": {"var": "$base"}},
        {
            "id": "twice-base-add",
            "op": "add",
            "var": "$twice",
            "value": {"var": "$base"},
        },
        {
            "id": "production-kind",
            "op": "if",
            "condition": {
                "op": "ge",
                "left": {"var": "$production"},
                "right": 0,
            },
            "then": [
                {
                    "id": "price",
                    "op": "set",
                    "var": "$price",
                    "value": {"var": "$quotient"},
                },
                {
                    "id": "price-add",
                    "op": "add",
                    "var": "$price",
                    "value": {"var": "$twice"},
                },
            ],
            "else": [
                {
                    "id": "price-building",
                    "op": "set",
                    "var": "$price",
                    "value": {"var": "$twice"},
                }
            ],
        },
        {
            "id": "neg-id",
            "op": "subtract",
            "var": "$neg_id",
            "value": {"var": "$production"},
        },
        {
            "id": "unit-doubling",
            "op": "if",
            "condition": {"op": "ge", "left": {"var": "$neg_id"}, "right": 22},
            "then": [
                {
                    "id": "double-unit-price",
                    "op": "add",
                    "var": "$price",
                    "value": {"var": "$price"},
                }
            ],
            "else": [],
        },
        {
            "id": "empty-box-doubling",
            "op": "if",
            "condition": {"op": "eq", "left": {"var": "$shield_box"}, "right": 0},
            "then": [
                {
                    "id": "double-empty-price",
                    "op": "add",
                    "var": "$price",
                    "value": {"var": "$price"},
                }
            ],
            "else": [],
        },
        {
            "id": "require-affordable",
            "op": "require",
            "condition": {
                "op": "ge",
                "left": {"var": "$treasury"},
                "right": {"var": "$price"},
            },
        },
        {
            "id": "complete-production",
            "op": "set",
            "var": "$shield_box",
            "value": {"var": "$t10"},
        },
        {
            "id": "debit-treasury",
            "op": "subtract",
            "var": "$treasury",
            "value": {"var": "$price"},
        },
    ]
    program = {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": values,
        "resources": {},
        "body": body,
    }
    validate_il(program)
    return program


def _contract(program: dict, evidence: dict) -> dict:
    return {
        "format": "fdisbull-block-contract-1",
        "name": "civ.city.buy.commit",
        "author": "civ-city-buy-slice",
        "inputs": {
            "shield_box": "i16",
            "treasury": "i16",
            "item_cost": "i16",
            "production": "i16",
        },
        "outputs": {"shield_box": "i16", "treasury": "i16"},
        "behavior": {"kind": "uil", "program": deepcopy(program)},
        "domain": {},
        "evidence": {
            "source": evidence,
            "boundary": {
                "guard": "treasury < price means no purchase (0x75D2).",
                "commit": "production completes: shield_box = 10 * item_cost; treasury -= price.",
                "price": "b = ClampInt(10*item_cost - shield_box, 0, 999); production >= 0 (unit) prices at 2b + i16(b*b)/20, production < 0 (building) at 2b; doubled when -production > 21 and when shield_box == 0.",
                "excluded": "The box text, the CIVIL DISORDER variant and the blinking CHANGE timer are outside this transition.",
            },
        },
    }


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
                    "item_cost": {"var": "$item_cost"},
                    "production": {"var": "$production"},
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
            "route": "R:0D12:7387 price, R:0D12:75D2 guard, R:0D12:75E5 commit",
            "price": "base = ClampInt(10*item_cost - shield_box, 0, 999); units add base*base/20, buildings do not",
            "doubling": "-production > 0x15 doubles buildings; shield_box == 0 doubles both",
            "commit": "0x75F6 word [city+0x70FA] = 10*item_cost; 0x7604 gold -= price",
            "unrecovered": "the exact Yes/No dialog call only; the cost tables are the unit record word +0x18 and the improvement record word +0x18 (both cost/10)",
        },
        "civ64_docs": {
            "repository": "Buyukcaglar/Civ64",
            "paths": ["docs/DOS-PROFILE.md row 87", "docs/dos/SCENES-PLAY.md 7.1"],
            "role": "crosswalk for the buy box text and the city record offsets",
        },
    }
    primitive = buy_program(initial)
    contract = _contract(primitive, evidence)

    with Project.create(project_path, source_path) as project:
        price = project.capture_snippet(
            "civ-city-buy-price",
            [{"address": PRICE_SITE, "size": PRICE_SNIPPET_SIZE}],
            evidence={
                "site": PRICE_SITE,
                "role": "price = 2b + b*b/20 with two doublings",
            },
            boundary="price derivation window; box text and dialog excluded",
            author="civ-city-buy-slice",
        )
        commit = project.capture_snippet(
            "civ-city-buy-commit",
            [{"address": COMMIT_SITE, "size": COMMIT_SNIPPET_SIZE}],
            evidence={
                "site": COMMIT_SITE,
                "role": "production completes; gold -= price",
            },
            boundary="treasury guard and commit stores",
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
                "source_to_uil": "guard and commit stores proven by disassembly; price derivation not modelled",
            },
            "evidence": {"price_snippet": price["id"], "commit_snippet": commit["id"]},
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
                "price": {
                    "id": price["id"],
                    "sha256": price["sha256"],
                    "site": PRICE_SITE,
                },
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
            "scope": "bounded buy guard and commit; price derivation supplied by the caller",
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
