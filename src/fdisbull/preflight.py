"""Lightweight installation/capability doctor.

Bounded preflight only: it never reads game inputs, creates an FDB, launches a
backend or target, searches the drive or hashes provider content. Reuse the
existing authored-target acceptance doctor (``fdisbull doctor``) for backend
execution; the two commands stay distinct by design.
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

from . import __version__
from .runtime_identity import identity as runtime_identity

_FORMAT = "fdisbull-preflight-1"


def _skills():
    from .cli import AGENT_SKILLS

    return {name: sorted(item["guides"]) for name, item in AGENT_SKILLS.items()}


def _distribution_identity():
    try:
        return {
            "distribution_version": importlib.metadata.version("fdisbull"),
            "runtime_version": __version__,
        }
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return {"distribution_version": None, "runtime_version": __version__}


def _skill_checks(expected):
    checks = []
    available = _skills()
    for name, references in sorted(expected.items()):
        present = available.get(name)
        if present is None:
            checks.append(
                {
                    "kind": "skill",
                    "name": name,
                    "status": "missing",
                    "expected": references,
                }
            )
        else:
            missing = [item for item in references if item not in present]
            checks.append(
                {
                    "kind": "skill",
                    "name": name,
                    "status": "ready",
                    "missing_references": missing,
                }
                if missing
                else {"kind": "skill", "name": name, "status": "ready"}
            )
    return checks


def _module_checks(expected):
    checks = []
    for module_name, attribute in sorted(expected.items()):
        try:
            module = __import__(module_name, fromlist=[attribute])
            present = hasattr(module, attribute)
        except (ImportError, OSError, ValueError):
            present = False
        checks.append(
            {
                "kind": "module",
                "name": module_name,
                "attribute": attribute,
                "status": "ready" if present else "missing",
            }
        )
    return checks


def _dependency_checks(expected):
    checks = []
    for distribution, requirement in sorted(expected.items()):
        try:
            installed = importlib.metadata.version(distribution)
        except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
            installed = None
        checks.append(
            {
                "kind": "dependency",
                "name": distribution,
                "status": "ready" if installed else "missing",
                "required": requirement,
                "installed": installed,
            }
        )
    return checks


def preflight(*, expectations, output=None):
    """Report ready/missing per expected feature against the imported install."""
    report = {
        "format": _FORMAT,
        "status": "running",
        "runtime_identity": runtime_identity(),
        "distribution": _distribution_identity(),
        "checks": [],
        "scope": "Installation preflight only; no backend or target execution.",
    }
    manifest_path = Path(expectations)
    try:
        manifest = json.loads(manifest_path.read_text())
    except OSError as error:
        report.update(
            status="missing_expectations",
            error=f"expectation manifest unreadable: {error}",
        )
        return report
    except ValueError as error:
        report.update(
            status="missing_expectations",
            error=f"expectation manifest is not valid JSON: {error}",
        )
        return report
    if not isinstance(manifest, dict):
        report.update(
            status="missing_expectations",
            error="expectation manifest must be a JSON object",
        )
        return report
    unknown_types = {
        item.get("type")
        for item in manifest.get("capabilities", [])
        if isinstance(item, dict)
        and item.get("type") not in ("skill", "module", "dependency")
    }
    if unknown_types:
        report.update(
            status="refused",
            error=f"unsupported capability type: {sorted(unknown_types)}",
        )
        return report
    for item in manifest.get("capabilities", []):
        kind = item.get("type")
        if kind == "skill":
            report["checks"].extend(
                _skill_checks({item["name"]: item.get("references", [])})
            )
        elif kind == "module":
            report["checks"].extend(_module_checks({item["name"]: item["attribute"]}))
        elif kind == "dependency":
            report["checks"].extend(
                _dependency_checks({item["name"]: item.get("requirement", "")})
            )
    ready = [item for item in report["checks"] if item["status"] == "ready"]
    missing = [item for item in report["checks"] if item["status"] == "missing"]
    report["summary"] = {
        "ready": len(ready),
        "missing": len(missing),
        "total": len(report["checks"]),
    }
    report["status"] = "ready" if not missing else "issues_found"
    if output is not None:
        path = Path(output)
        path.write_text(json.dumps(report, indent=2) + "\n")
        report["written_to"] = str(path)
    return report
