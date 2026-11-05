from copy import deepcopy
import json
import subprocess

import pytest

from fdisbull.uil_link import make_module, make_provider, make_requirement

from demo import DOMAIN, fixtures, run
from registry import Registry


@pytest.fixture
def prepared(tmp_path):
    catalog, group, module, provider, representation = fixtures()
    with Registry(tmp_path / "private.sqlite", create=True) as registry:
        registry.import_catalog(catalog)
        registry.register_components([module], [provider], target="linux-x64")
        yield registry, catalog, group, module, provider, representation


def ask(registry, group, target="linux-x64", domain=DOMAIN):
    return registry.query(group["semantic_id"], target, domain=domain)


def test_actual_catalog_preserves_distinct_source_representations(prepared):
    registry, catalog, group, module, provider, representation = prepared
    assert len(catalog["groups"]) == 1
    assert len(group["implementations"]) == 2
    assert {item["language"] for item in group["implementations"]} == {"c-u16", "python-u16"}
    for implementation in group["implementations"]:
        document = {**representation, "implementation": implementation["id"],
                    "representation_language": implementation["language"]}
        registry.register_representation(document)
    result = ask(registry, group)
    assert len(result["representations"]) == 2
    assert len({row["implementation"] for row in result["representations"]}) == 2
    assert all(row["link_lock_sha256"] for row in result["representations"])
    assert result["next_action"] == "build"


def test_unknown_contract_is_recovery_not_sweding(prepared):
    registry, *_ = prepared
    result = registry.query("semantic:" + "0" * 64, "linux-x64", domain=DOMAIN)
    assert result["next_action"] == "recover-contract"
    assert "task" not in result


def test_missing_domain_is_explicit(prepared):
    registry, _, group, *_ = prepared
    assert ask(registry, group, domain=None)["next_action"] == "declare-domain"


def test_missing_join_does_not_hide_known_source_model_implementations(prepared):
    registry, _, group, *_ = prepared
    result = ask(registry, group)
    assert result["next_action"] == "assess-bind-existing"
    assert {item["id"] for item in result["known_implementations"]} == {item["id"] for item in group["implementations"]}
    assert {item["language"] for item in result["known_implementations"]} == {"c-u16", "python-u16"}
    assert len(result["unbound_implementation_ids"]) == 2
    assert result["contract"]["function"] == group["function"]
    assert result["absence_established"] is False
    assert "task" not in result


def test_explicit_swede_request_preserves_contract_and_existing_alternatives(prepared):
    registry, _, group, _, _, document = prepared
    exclusions = [{"implementation": document["implementation"], "reason": "An additional backing is requested."}]
    task = registry.generate_swede_task(group["semantic_id"], "linux-x64", domain=DOMAIN,
                                        reason="Explore another implementation.", candidate_exclusions=exclusions)
    assert task["kind"] == "swede"
    assert task["contract"]["function"] == group["function"]
    assert task["contract"]["constants"] == group["constants"]
    assert len(task["known_implementations"]) == 2
    assert task["candidate_exclusions"] == [{**exclusions[0], "assessment_status": "caller-declared"}]
    assert task["domain"] == DOMAIN
    assert task["absence_established"] is False
    assert task["execution_authorized"] is False


def test_swede_request_refuses_unknown_contract_or_unrelated_exclusions(prepared):
    registry, _, group, *_ = prepared
    with pytest.raises(ValueError, match="known validated contract"):
        registry.generate_swede_task("semantic:" + "0" * 64, "linux-x64", domain=DOMAIN,
                                     reason="Additional backing.", candidate_exclusions=[])
    with pytest.raises(ValueError, match="unknown matching implementation"):
        registry.generate_swede_task(group["semantic_id"], "linux-x64", domain=DOMAIN,
                                     reason="Additional backing.", candidate_exclusions=[{
                                         "implementation": "implementation:" + "0" * 64,
                                         "reason": "Unrelated candidate."}])


def test_actual_demo_persists_and_changes_next_action(tmp_path):
    result = run(tmp_path / "demo.sqlite")
    assert result["before"]["next_action"] == "assess-bind-existing"
    assert result["after_reopen"]["next_action"] == "build"
    assert result["registration"]["admission"] == "structural-only"
    assert result["explicit_additional_swede_task"]["kind"] == "swede"
    assert result["explicit_additional_swede_task"]["absence_established"] is False
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("availability,backend,evidence,action", [
    ("metadata-only", "available", [], "locate-source"),
    ("source-present", "unavailable", [], "prepare-backend"),
    ("source-present", "unknown", [], "prepare-backend"),
    ("source-present", "available", [], "build"),
    ("artifact-present", "available", [], "qualify"),
    ("artifact-present", "available", [{"scope": "target-execution", "sha256": "a" * 64}], "review-evidence"),
])
def test_guidance_never_promotes_submitted_claims(prepared, availability, backend, evidence, action):
    registry, _, group, _, _, document = prepared
    document.update(availability=availability, backend=backend, evidence=evidence)
    if availability == "artifact-present":
        document["artifact_sha256"] = "b" * 64
    registry.register_representation(document)
    result = ask(registry, group)
    assert result["next_action"] == action
    assert result["execution_authorized"] is False
    row = result["representations"][0]
    assert row["execution_authorized"] is False
    assert row["association_status"] == "submitted-declaration"
    assert row["evidence_status"] == "unverified-references"
    assert row["evidence"] == evidence


def test_wrong_target_stays_visible_and_requires_portability_assessment(prepared):
    registry, _, group, _, _, document = prepared
    registry.register_representation(document)
    result = ask(registry, group, target="macos-arm64")
    assert result["next_action"] == "assess-target"
    assert result["representations"][0]["reasons"] == ["target_mismatch"]
    assert result["representations"][0]["next_action"] == "assess-target"
    assert len(result["known_implementations"]) == 2
    assert result["absence_established"] is False
    assert "task" not in result


def test_domain_mismatch_requires_qualification_not_inferred_containment(prepared):
    registry, _, group, _, _, document = prepared
    registry.register_representation(document)
    result = ask(registry, group, domain={"kind": "declared-subset", "description": "x in 0..8"})
    assert result["next_action"] == "qualify-domain"
    assert result["representations"][0]["reasons"] == ["domain_not_established"]


def test_actual_core_abi_matching_rejects_name_only_match(prepared):
    registry, _, group, _, _, document = prepared
    mismatched = make_requirement("core.add", inputs=[{"type": "u16"}, {"type": "u16"}],
                                 outputs=[{"type": "u16"}], abi="different-abi")
    wrong = make_provider("wrong.abi", [mismatched], target="linux-x64")
    registry.register_components([], [wrong], target="linux-x64")
    registry.register_representation({**document, "provider": wrong["id"]})
    result = ask(registry, group)
    assert result["next_action"] == "repair-module-plan"
    assert "no exact module requirement" in result["representations"][0]["resolution_error"]


def test_core_dependency_ambiguity_remains_unresolved(prepared):
    registry, _, group, _, _, document = prepared
    work = make_requirement("example.work")
    leaf = make_requirement("example.leaf")
    module = make_module("ambiguous.root", [work])
    parent = make_provider("parent", [work], target="linux-x64", requires=[leaf])
    first = make_provider("leaf.one", [leaf], target="linux-x64")
    second = make_provider("leaf.two", [leaf], target="linux-x64")
    registry.register_components([module], [parent, first, second], target="linux-x64")
    registry.register_representation({**document, "module": module["id"], "provider": parent["id"]})
    result = ask(registry, group)
    assert result["next_action"] == "repair-module-plan"
    assert "ambiguous intrinsic" in result["representations"][0]["resolution_error"]


def test_core_cycle_check_remains_active(prepared):
    registry, _, group, _, _, document = prepared
    req = make_requirement("example.recursive")
    module = make_module("recursive.root", [req])
    provider = make_provider("recursive.provider", [req], target="linux-x64", requires=[req])
    registry.register_components([module], [provider], target="linux-x64")
    registry.register_representation({**document, "module": module["id"], "provider": provider["id"]})
    result = ask(registry, group)
    assert result["next_action"] == "repair-module-plan"
    assert "cycle" in result["representations"][0]["resolution_error"]


def test_idempotent_intake_and_immutable_revision(prepared):
    registry, catalog, group, _, _, document = prepared
    assert registry.import_catalog(catalog)["created"] is False
    first = registry.register_representation(document)
    assert registry.register_representation(document) == {**first, "created": False}
    updated = registry.register_representation({**document, "backend": "unavailable"})
    assert updated["id"] != first["id"]
    assert len(ask(registry, group)["representations"]) == 2


def test_deterministic_result_independent_of_insertion_order(tmp_path):
    catalog, group, module, provider, document = fixtures()
    variants = [{**document, "origin": origin} for origin in ("authored.second", "authored.first")]
    results = []
    for index, ordering in enumerate((variants, list(reversed(variants)))):
        with Registry(tmp_path / (str(index) + ".sqlite"), create=True) as registry:
            registry.import_catalog(catalog)
            registry.register_components([module], [provider], target="linux-x64")
            for variant in ordering:
                registry.register_representation(variant)
            results.append(ask(registry, group))
    assert results[0] == results[1]


def test_snapshot_digest_changes_while_same_query_digest_remains(prepared):
    registry, _, group, _, _, document = prepared
    before = ask(registry, group)
    registry.register_representation(document)
    after = ask(registry, group)
    assert before["query_sha256"] == after["query_sha256"]
    assert before["snapshot_sha256"] != after["snapshot_sha256"]
    assert not registry.db.in_transaction


@pytest.mark.parametrize("change", [
    {"implementation": "implementation:bad"},
    {"implementation": "implementation:" + "0" * 64},
    {"target": "macos-arm64"},
    {"distribution": "approved-public"},
    {"qualified": True},
    {"evidence": [{"scope": "target-execution", "sha256": "a" * 64, "passed": True}]},
    {"availability": "artifact-present"},
    {"artifact_sha256": "b" * 64},
])
def test_malformed_or_authority_claim_fields_refuse(prepared, change):
    registry, _, _, _, _, document = prepared
    with pytest.raises(ValueError):
        registry.register_representation({**document, **change})


def test_stale_catalog_identity_refuses(prepared):
    registry, catalog, *_ = prepared
    damaged = deepcopy(catalog)
    damaged["groups"][0]["constants"][0] = "2"
    with pytest.raises(ValueError, match="identity mismatch"):
        registry.import_catalog(damaged)


def test_stale_provider_identity_refuses(prepared):
    registry, _, _, _, provider, _ = prepared
    with pytest.raises(ValueError, match="stale"):
        registry.register_components([], [{**provider, "target": "macos-arm64"}], target="macos-arm64")


def test_sql_document_tampering_is_rechecked(prepared):
    registry, _, group, _, _, document = prepared
    receipt = registry.register_representation(document)
    damaged = {**document, "origin": "modified after intake"}
    registry.db.execute("UPDATE documents SET document=? WHERE id=?",
                        (json.dumps(damaged, sort_keys=True, separators=(",", ":")), receipt["id"]))
    registry.db.commit()
    with pytest.raises(ValueError, match="identity mismatch"):
        ask(registry, group)


def test_private_database_refuses_git_location(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    with pytest.raises(ValueError, match="outside Git"):
        Registry(checkout / "private.sqlite", create=True)
    assert not (checkout / "private.sqlite").exists()


def test_create_does_not_overwrite_existing_database(tmp_path):
    path = tmp_path / "existing.sqlite"
    with Registry(path, create=True):
        pass
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        Registry(path, create=True)
    assert path.read_bytes() == before
