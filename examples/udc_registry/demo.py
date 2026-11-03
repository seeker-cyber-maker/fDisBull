"""Authored search -> assess existing descriptors -> register -> build plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_link import make_module, make_provider, make_requirement

from registry import REPRESENTATION, Registry


DOMAIN = {"kind": "full-typed-domain"}


def fixtures():
    catalog = build_catalog([
        {"language": "c-u16", "source_text": "ax += 1;", "inputs": ["ax"], "outputs": ["ax"]},
        {"language": "python-u16", "source_text": "ax = (ax + 1) & 65535", "inputs": ["ax"], "outputs": ["ax"]},
    ])
    group = catalog["groups"][0]
    requirement = make_requirement("core.add", inputs=[{"type": "u16"}, {"type": "u16"}], outputs=[{"type": "u16"}])
    module = make_module("authored.increment", [requirement], metadata={"semantic_id": group["semantic_id"]})
    provider = make_provider("authored.example.provider", [requirement], target="linux-x64")
    implementation = next(item for item in group["implementations"] if item["language"] == "c-u16")
    representation = {"format": REPRESENTATION, "implementation": implementation["id"],
                      "module": module["id"], "provider": provider["id"], "target": "linux-x64",
                      "representation_language": "c", "domain": DOMAIN, "availability": "source-present",
                      "backend": "available", "origin": "authored arithmetic example; availability is a declaration",
                      "distribution": "authored-review-requested", "evidence": []}
    return catalog, group, module, provider, representation


def run(path):
    catalog, group, module, provider, representation = fixtures()
    with Registry(path, create=True) as registry:
        registry.import_catalog(catalog)
        before = registry.query(group["semantic_id"], "linux-x64", domain=DOMAIN)
        registry.register_components([module], [provider], target="linux-x64")
        receipt = registry.register_representation(representation)
    with Registry(path) as reopened:
        after = reopened.query(group["semantic_id"], "linux-x64", domain=DOMAIN)
        additional = reopened.generate_swede_task(
            group["semantic_id"], "linux-x64", domain=DOMAIN,
            reason="Author requests an additional implementation experiment while retaining existing alternatives.",
            candidate_exclusions=[{"implementation": representation["implementation"],
                                   "reason": "Retain this existing C representation as a comparison baseline; a new backing was requested."}])
    return {"before": before, "registration": receipt, "after_reopen": after,
            "explicit_additional_swede_task": additional,
            "note": "The source example was supplied by the author. No agent generation, compilation, receipt verification or native execution occurred.",
            "execution_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="New private SQLite path outside Git; omit for a temporary demonstration.")
    args = parser.parse_args()
    if args.database is None:
        with tempfile.TemporaryDirectory(prefix="udc-registry-study-") as directory:
            result = run(Path(directory) / "registry.sqlite")
    else:
        result = run(args.database)
    print(json.dumps(result, indent=2, sort_keys=True))
