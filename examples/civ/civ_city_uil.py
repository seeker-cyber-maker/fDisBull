"""Build the bounded Civ city UIL scene and an executable UDC shell.

This is an authored bridge around one recovered city-production boundary.  It
keeps the original DOS bytes in the private fDisBull project, uses a retained
city-process snippet as provenance, and emits a new Linux x86-64 shell from the
shared UIL model.  It does not claim to compile the whole DOS city screen or
replace its VGA/resource providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

from fdisbull.interaction_il import validate_il
from fdisbull.project import Project
from fdisbull.udc_layers import (
    build_selection_shell,
    register_contract,
    register_layer,
    select_layers,
)

EXPECTED_UNPACKED_SHA256 = (
    "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"
)
CIVD_COMMIT = "d9214fcd36aa6003d28aae60c3974b665f752280"
CIV64_COMMIT = "4e46572d727544722d90c24dc2ce51a9c6d22f15"
CITY_PROCESS_ADDRESS = "1D12:0045"
CITY_PROCESS_SNIPPET_SIZE = 64


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _file_evidence(
    path: Path | None, *, repository: str, commit: str, source_path: str
) -> dict:
    if path is None:
        return {
            "repository": repository,
            "commit": commit,
            "path": source_path,
            "status": "not supplied",
        }
    path = path.resolve(strict=True)
    return {
        "repository": repository,
        "commit": commit,
        "path": source_path,
        "sha256": _sha256(path),
        "status": "local hash observed",
    }


def city_scene(path: Path | None = None) -> dict:
    """Read the committed partial city-screen UIL scene."""
    path = path or Path(__file__).with_name("civ_city_scene.json")
    with path.open("rb") as stream:
        document = json.load(stream)
    return document


def _primitive_program(initial: dict | None = None) -> dict:
    values = {
        "$shield_box": {"type": "i16", "initial": 0},
        "$shield_delta": {"type": "i16", "initial": 3},
        "$disorder": {"type": "bool", "initial": False},
        "$sanitized": {"type": "bool", "initial": True},
    }
    if initial is not None:
        if not isinstance(initial, dict) or set(initial) - set(values):
            raise ValueError("initial state contains an unknown Civ city variable")
        for name, value in initial.items():
            values[name]["initial"] = value
    program = {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": values,
        "resources": {},
        "body": [
            {
                "id": "require-sanitized-input",
                "op": "require",
                "condition": {"op": "eq", "left": {"var": "$sanitized"}, "right": True},
            },
            {
                "id": "disorder-or-accumulate",
                "op": "if",
                "condition": {"op": "eq", "left": {"var": "$disorder"}, "right": True},
                "then": [
                    {
                        "id": "zero-disorder-contribution",
                        "op": "set",
                        "var": "$shield_box",
                        "value": 0,
                    }
                ],
                "else": [
                    {
                        "id": "add-shield-contribution",
                        "op": "add",
                        "var": "$shield_box",
                        "value": {"var": "$shield_delta"},
                    }
                ],
            },
        ],
    }
    validate_il(program)
    return program


def _contract(program: dict, evidence: dict) -> dict:
    return {
        "format": "fdisbull-block-contract-1",
        "name": "civ.city.production.sanitized-shield-step",
        "author": "civ-city-uil-slice",
        "inputs": {
            "shield_box": "i16",
            "shield_delta": "i16",
            "disorder": "bool",
            "sanitized": "bool",
        },
        "outputs": {"shield_box": "i16"},
        "behavior": {"kind": "uil", "program": deepcopy(program)},
        "domain": {},
        "evidence": {
            "source": evidence,
            "boundary": {
                "reset": "The caller supplies sanitized=true after applying the source reset rule shield_box > 999 or shield_box < 0 -> 0.",
                "disorder": "The source sets the production contribution to zero in disorder; this model then leaves shield_box at zero.",
                "scope": "One bounded state transition; not a complete city_process model.",
            },
        },
    }


def _module_program(contract_id: str, primitive: dict) -> dict:
    return {
        "format": "fdisbull-module-uil-1",
        "role": "uil",
        "variables": deepcopy(primitive["variables"]),
        "resources": {},
        "body": [
            {
                "id": "invoke-city-shield-step",
                "op": "invoke",
                "binding": "city-production",
                "contract": contract_id,
                "inputs": {
                    "shield_box": {"var": "$shield_box"},
                    "shield_delta": {"var": "$shield_delta"},
                    "disorder": {"var": "$disorder"},
                    "sanitized": {"var": "$sanitized"},
                },
                "outputs": {"shield_box": "$shield_box"},
            }
        ],
    }


def build_city_udc(
    source: str | Path,
    destination: str | Path,
    *,
    project_path: str | Path | None = None,
    civd_citymgt: str | Path | None = None,
    civd_civ_h: str | Path | None = None,
    civd_production_doc: str | Path | None = None,
    initial: dict | None = None,
    target: str = "linux-x64",
) -> dict:
    """Build a source-bound UDC shell (Linux x86-64 or macOS arm64) for the city step.

    ``source`` must be the exact unpacked 474.05/475.05 root produced by
    ``civ_exepack.py``.  The destination is intentionally required to be a new
    directory outside the Git worktree by the fDisBull shell builder.
    """
    source_path = Path(source).expanduser().resolve(strict=True)
    source_sha256 = _sha256(source_path)
    if source_sha256 != EXPECTED_UNPACKED_SHA256:
        raise ValueError(
            "Civ city UDC requires the pinned unpacked root "
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

    source_evidence = {
        "original_root": {
            "sha256": source_sha256,
            "bytes": source_path.stat().st_size,
            "file": source_path.name,
        },
        "civd_citymgt": _file_evidence(
            Path(civd_citymgt) if civd_citymgt is not None else None,
            repository="sjmelia/civd",
            commit=CIVD_COMMIT,
            source_path="src/CITYMGT.C",
        ),
        "civd_civ_h": _file_evidence(
            Path(civd_civ_h) if civd_civ_h is not None else None,
            repository="sjmelia/civd",
            commit=CIVD_COMMIT,
            source_path="src/CIV.H",
        ),
        "civd_production": _file_evidence(
            Path(civd_production_doc) if civd_production_doc is not None else None,
            repository="sjmelia/civd",
            commit=CIVD_COMMIT,
            source_path="book/src/city/production.md",
        ),
        "civ64_analysis": {
            "repository": "Buyukcaglar/Civ64",
            "commit": CIV64_COMMIT,
            "route": "R:0D12:0045 -> fDisBull MZ runtime 1D12:0045",
            "status": "analysis reference; no Civ64 source bytes published",
        },
    }
    primitive = _primitive_program(initial)
    contract = _contract(primitive, source_evidence)

    with Project.create(project_path, source_path) as project:
        snippet = project.capture_snippet(
            "civ-city-process-prologue",
            [{"address": CITY_PROCESS_ADDRESS, "size": CITY_PROCESS_SNIPPET_SIZE}],
            evidence={
                "civ64_route": "R:0D12:0045 translated with MZ load segment 0x1000",
                "fdisbull_context": "x86:16:little:cs=1d12",
                "source_identity": source_sha256,
            },
            boundary="candidate city_process entry; prologue only; not a complete handler",
            author="civ-city-uil-slice",
        )
        contract_record = register_contract(
            project, contract, author="civ-city-uil-slice"
        )
        contract_id = contract_record["id"]
        layer = {
            "format": "fdisbull-udl-layer-1",
            "name": "civ-city-shield-step-uil",
            "author": "civ-city-uil-slice",
            "contract": contract_id,
            "snippet": snippet["id"],
            "implementation": {"backend": "uil", "program": deepcopy(primitive)},
            "assurance": {
                "kind": "candidate-source-bound-model",
                "source_to_uil": "not proven",
                "native_execution": "target artifact only until a Linux x86-64 runtime is supplied",
            },
            "evidence": {"snippet": snippet["id"], "source": source_evidence},
        }
        layer_record = register_layer(project, layer, author="civ-city-uil-slice")
        layer_id = layer_record["id"]
        module = _module_program(contract_id, primitive)
        selection_record = select_layers(
            project,
            "civ-city-production-selection",
            {"city-production": layer_id},
            program=module,
            target=target,
            author="civ-city-uil-slice",
        )
        selection_id = selection_record["id"]
        plan = {
            "format": "fdisbull-native-shell-1",
            "entry": "main",
            "state": deepcopy(primitive["variables"]),
            "resources": {},
            "functions": {
                "main": {"body": [{"op": "call", "binding": "city-production"}]}
            },
            "evidence": {"source": source_evidence, "snippet": snippet["id"]},
        }
        build = build_selection_shell(
            project,
            selection_id,
            plan,
            destination_path,
            target=target,
            capture_state=(target != "macos-arm64"),
        )
        return {
            "format": "fdisbull-civ-city-udc-build-1",
            "source": source_evidence["original_root"],
            "snippet": {
                "id": snippet["id"],
                "sha256": snippet["sha256"],
                "address": CITY_PROCESS_ADDRESS,
                "size": CITY_PROCESS_SNIPPET_SIZE,
            },
            "contract": {
                "id": contract_id,
                "sha256": contract_record["sha256"],
                "name": contract["name"],
            },
            "selection": {"id": selection_id, "sha256": selection_record["sha256"]},
            "module": module,
            "native_build": build,
            "qualification": build["qualification"],
            "scope": "bounded source-linked city shield transition; no VGA provider or whole-game equivalence claim",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the bounded Civ city UIL/UDC module"
    )
    parser.add_argument("source", help="exact generated CIV_UNP.EXE")
    parser.add_argument("destination", help="new output directory outside Git")
    parser.add_argument("--project", help="new private fDisBull project path")
    parser.add_argument(
        "--civd-citymgt", help="local civd src/CITYMGT.C for provenance hashing"
    )
    parser.add_argument(
        "--civd-civ-h", help="local civd src/CIV.H for provenance hashing"
    )
    parser.add_argument(
        "--civd-production-doc", help="local civd production.md for provenance hashing"
    )
    parser.add_argument("--state", help="JSON object overriding initial module state")
    parser.add_argument(
        "--target",
        choices=("linux-x64", "macos-arm64"),
        default="linux-x64",
        help="native output target; macOS arm64 links libSystem and reports on stdout",
    )
    args = parser.parse_args(argv)
    try:
        initial = None
        if args.state:
            with Path(args.state).open("rb") as stream:
                initial = json.load(stream)
        receipt = build_city_udc(
            args.source,
            args.destination,
            project_path=args.project,
            civd_citymgt=args.civd_citymgt,
            civd_civ_h=args.civd_civ_h,
            civd_production_doc=args.civd_production_doc,
            initial=initial,
            target=args.target,
        )
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        print(
            json.dumps(
                {
                    "format": "fdisbull-civ-city-udc-build-1",
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
