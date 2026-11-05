"""Experimental private planning index over existing fDisBull identities.

This example stores documents and submitted assertions. It never loads a
provider, executes a submission, verifies a receipt, or grants execution or
publication authority. Existing UIL/catalog/link validators remain authoritative.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import re
import sqlite3

from fdisbull.common_uil import FORMAT as PROFILE, canonical_bytes, digest
from fdisbull.uil_catalog import validate_catalog
from fdisbull.uil_link import TARGETS, describe_components, resolve_modules


FORMAT = "udc-registry-study-1"
REPRESENTATION = "udc-registry-representation-study-1"
MAX_DOCUMENTS = 512
MAX_DOCUMENT_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = {"catalog", "module", "provider", "representation"}
_DDL = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents(
    kind TEXT NOT NULL, id TEXT PRIMARY KEY, document TEXT NOT NULL,
    CHECK(kind IN ('catalog','module','provider','representation')));
CREATE INDEX document_kind ON documents(kind,id);
"""


def _json(document):
    raw = canonical_bytes(document)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("study document exceeds 1 MiB")
    return raw.decode("utf-8")


def _fields(document, required, optional=()):
    if (type(document) is not dict or not set(required) <= document.keys()
            or document.keys() - set(required) - set(optional)):
        raise ValueError("invalid study fields")


def _text(value, name, limit=256):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(char) < 32 for char in value)):
        raise ValueError("invalid " + name)
    return value


def _identifier(value, prefix):
    if (type(value) is not str or not value.startswith(prefix + ":")
            or not _SHA.fullmatch(value[len(prefix) + 1:])):
        raise ValueError("invalid " + prefix + " identity")
    return value


def _domain(value):
    _fields(value, ("kind",), ("description",))
    if value["kind"] == "full-typed-domain":
        if set(value) != {"kind"}:
            raise ValueError("full typed domain has no extra fields")
    elif value["kind"] == "declared-subset":
        _text(value.get("description"), "domain description", 1024)
    else:
        raise ValueError("unsupported study domain declaration")
    return deepcopy(value)


class Registry:
    """One private SQLite file; bounded, explicit writes and sorted reads."""

    def __init__(self, path, *, create=False):
        self.path = Path(path).expanduser().resolve()
        # A .git file identifies a worktree; a real Git directory has HEAD.
        # Empty marker directories in managed environments are not checkouts.
        if any((parent / ".git").is_file() or (parent / ".git" / "HEAD").is_file()
               for parent in self.path.parents):
            raise ValueError("private study databases must stay outside Git")
        if create:
            with self.path.open("xb"):
                pass
            self.path.chmod(0o600)
        elif not self.path.is_file():
            raise ValueError("registry does not exist; create it explicitly")
        self.db = sqlite3.connect(self.path)
        try:
            if create:
                self.db.executescript(_DDL)
                self.db.execute("INSERT INTO metadata VALUES('format',?)", (FORMAT,))
                self.db.commit()
            row = self.db.execute("SELECT value FROM metadata WHERE key='format'").fetchone()
            if row is None or row[0] != FORMAT:
                raise ValueError("unsupported study database")
        except Exception:
            self.db.close()
            if create:
                self.path.unlink()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.db.close()

    @contextmanager
    def _read_view(self):
        if self.db.in_transaction:
            raise ValueError("query requires no active caller write transaction")
        self.db.execute("BEGIN")
        try:
            yield
        finally:
            self.db.rollback()

    def _put(self, kind, identity, document):
        assert kind in _KINDS
        raw = _json(document)
        row = self.db.execute("SELECT kind,document FROM documents WHERE id=?", (identity,)).fetchone()
        if row is not None:
            if row != (kind, raw):
                raise ValueError("immutable record identity collision")
            return False
        if self.db.execute("SELECT count(*) FROM documents").fetchone()[0] >= MAX_DOCUMENTS:
            raise ValueError("study database document budget exceeded")
        self.db.execute("INSERT INTO documents VALUES(?,?,?)", (kind, identity, raw))
        return True

    def _documents(self, kind):
        rows = self.db.execute("SELECT id,document FROM documents WHERE kind=? ORDER BY id", (kind,)).fetchall()
        if len(rows) > MAX_DOCUMENTS:
            raise ValueError("study database document budget exceeded")
        result = []
        for identity, raw in rows:
            if len(raw.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("stored document exceeds budget")
            document = json.loads(raw)
            if _json(document) != raw:
                raise ValueError("stored document is not canonical")
            expected = ("catalog-study:" + digest(document) if kind == "catalog" else
                        "representation-study:" + digest(document) if kind == "representation" else
                        document.get("id"))
            if identity != expected:
                raise ValueError("stored document identity mismatch")
            result.append((identity, document))
        return result

    def import_catalog(self, catalog):
        """Admit an existing catalog locally; UIL bodies may themselves be private."""
        validate_catalog(catalog)
        identity = "catalog-study:" + digest(catalog)
        with self.db:
            created = self._put("catalog", identity, catalog)
        return {"id": identity, "created": created, "admission": "existing-catalog-validator",
                "distribution": "local-only", "execution_authorized": False}

    def register_components(self, modules, providers, *, target):
        """Validate declarations through the public core API; no providers are loaded."""
        choices = describe_components(modules, providers, target=target)
        with self.db:
            for kind, documents in (("module", modules), ("provider", providers)):
                for document in documents:
                    self._put(kind, document["id"], document)
        return {"resolution": choices["resolution"], "distribution": "local-only",
                "admission": "existing-component-validator", "execution_authorized": False}

    def _snapshot(self):
        groups, implementations = {}, {}
        for _, catalog in self._documents("catalog"):
            validate_catalog(catalog)
            for group in catalog["groups"]:
                groups[group["semantic_id"]] = group
                for implementation in group["implementations"]:
                    implementations[implementation["id"]] = (group["semantic_id"], implementation)
        modules = dict(self._documents("module"))
        providers = dict(self._documents("provider"))
        # Readback reuses core identity checks, even if no query candidates exist.
        describe_components(list(modules.values()), list(providers.values()), target=TARGETS[0])
        return groups, implementations, modules, providers

    def _representation(self, document, snapshot):
        _fields(document, ("format", "implementation", "module", "provider", "target",
                           "representation_language", "domain", "availability", "backend",
                           "origin", "distribution", "evidence"), ("artifact_sha256",))
        if document["format"] != REPRESENTATION:
            raise ValueError("unsupported representation study format")
        _, implementations, modules, providers = snapshot
        for field, prefix, records in (("implementation", "implementation", implementations),
                                       ("module", "module", modules), ("provider", "provider", providers)):
            if _identifier(document[field], prefix) not in records:
                raise ValueError("unknown " + field + " identity")
        if document["target"] not in TARGETS or providers[document["provider"]]["target"] != document["target"]:
            raise ValueError("representation target differs from provider")
        _text(document["representation_language"], "representation language", 64)
        _text(document["origin"], "origin", 1024)
        _domain(document["domain"])
        if document["availability"] not in ("metadata-only", "source-present", "artifact-present"):
            raise ValueError("invalid declared availability")
        if document["backend"] not in ("unknown", "unavailable", "available"):
            raise ValueError("invalid declared backend state")
        if document["distribution"] not in ("local-only", "authored-review-requested"):
            raise ValueError("this study grants no distribution permission")
        evidence = document["evidence"]
        if type(evidence) is not list or len(evidence) > 32:
            raise ValueError("bounded submitted evidence list required")
        for item in evidence:
            _fields(item, ("scope", "sha256"))
            if item["scope"] not in ("source-model", "model-model", "build", "target-execution"):
                raise ValueError("unknown evidence scope")
            if type(item["sha256"]) is not str or not _SHA.fullmatch(item["sha256"]):
                raise ValueError("invalid evidence reference")
        if "artifact_sha256" in document:
            if type(document["artifact_sha256"]) is not str or not _SHA.fullmatch(document["artifact_sha256"]):
                raise ValueError("invalid artifact reference")
        if (document["availability"] == "artifact-present") != ("artifact_sha256" in document):
            raise ValueError("only artifact-present declarations require an artifact reference")
        _json(document)

    def register_representation(self, document):
        """Record a submitted association; validation does not verify the association."""
        self._representation(document, self._snapshot())
        identity = "representation-study:" + digest(document)
        with self.db:
            created = self._put("representation", identity, document)
        return {"id": identity, "created": created, "admission": "structural-only",
                "association_status": "submitted-declaration", "evidence_status": "unverified-references",
                "distribution": document["distribution"], "execution_authorized": False}

    @staticmethod
    def _plan(document, modules, providers, target):
        module, provider = modules[document["module"]], providers[document["provider"]]
        offered = {requirement["id"] for requirement in provider["provides"]}
        pins = {requirement["id"]: provider["id"] for requirement in module["requires"]
                if requirement["id"] in offered}
        if not pins:
            raise ValueError("associated provider satisfies no exact module requirement")
        return resolve_modules([module], list(providers.values()), target=target, pins={module["id"]: pins})

    def query(self, semantic_id, target, *, domain=None):
        """Plan against one pinned SQLite read view; never infer global absence."""
        with self._read_view():
            return self._query(semantic_id, target, domain=domain)

    def _query(self, semantic_id, target, *, domain=None):
        _identifier(semantic_id, "semantic")
        if target not in TARGETS:
            raise ValueError("unsupported native study target")
        domain = None if domain is None else _domain(domain)
        snapshot = self._snapshot()
        groups, implementations, modules, providers = snapshot
        rows = []
        for identity, document in self._documents("representation"):
            self._representation(document, snapshot)
            if implementations[document["implementation"]][0] != semantic_id:
                continue
            reasons, lock = [], None
            if document["target"] != target:
                reasons.append("target_mismatch")
                action = "assess-target"
            else:
                try:
                    lock = self._plan(document, modules, providers, target)
                except ValueError as exc:
                    reasons.append("module_resolution_failed")
                    action = "repair-module-plan"
                    link_error = str(exc)
                else:
                    link_error = None
                    if domain is not None and document["domain"] != domain:
                        reasons.append("domain_not_established")
                        action = "qualify-domain"
                    elif document["backend"] != "available":
                        reasons.append("backend_not_declared_available")
                        action = "prepare-backend"
                    elif document["availability"] == "metadata-only":
                        reasons.append("source_or_artifact_unavailable")
                        action = "locate-source"
                    elif document["availability"] == "source-present":
                        reasons.append("build_required")
                        action = "build"
                    elif not document["evidence"]:
                        reasons.append("qualification_missing")
                        action = "qualify"
                    else:
                        reasons.append("submitted_evidence_unverified")
                        action = "review-evidence"
            row = {"id": identity, "implementation": document["implementation"],
                   "module": document["module"], "provider": document["provider"],
                   "target": document["target"], "language": document["representation_language"],
                   "availability": document["availability"], "backend": document["backend"],
                   "domain": deepcopy(document["domain"]), "origin": document["origin"],
                   "distribution": document["distribution"], "evidence": deepcopy(document["evidence"]),
                   "association_status": "submitted-declaration", "evidence_status": "unverified-references",
                   "reasons": reasons, "next_action": action, "execution_authorized": False}
            if "artifact_sha256" in document:
                row["artifact_sha256"] = document["artifact_sha256"]
            if lock is not None:
                row["link_lock_sha256"] = lock["sha256"]
            if "module_resolution_failed" in reasons:
                row["resolution_error"] = link_error
            rows.append(row)
        priorities = {name: index for index, name in enumerate(("review-evidence", "qualify", "build",
                      "prepare-backend", "qualify-domain", "repair-module-plan", "locate-source", "assess-target"))}
        rows.sort(key=lambda row: (priorities[row["next_action"]], row["id"]))
        known = []
        for identity, (meaning, implementation) in sorted(implementations.items()):
            if meaning != semantic_id:
                continue
            bound = [row["id"] for row in rows if row["implementation"] == identity]
            target_bound = [row["id"] for row in rows if row["implementation"] == identity and row["target"] == target]
            known.append({"id": identity, "language": implementation["language"],
                          "source": deepcopy(implementation["source"]),
                          "source_assurance_declaration": implementation["assurance"],
                          "representation_ids": sorted(bound), "target_representation_ids": sorted(target_bound),
                          "association_status": "submitted-bindings" if bound else "unbound",
                          "next_action": "inspect-bindings" if target_bound else "assess-target" if bound else "assess-bind-existing",
                          "execution_authorized": False})
        if semantic_id not in groups:
            action = "recover-contract"
        elif domain is None:
            action = "declare-domain"
        else:
            action = rows[0]["next_action"] if rows else "assess-bind-existing"
        snapshot_ids = [{"kind": kind, "id": identity} for kind, identity in
                        self.db.execute("SELECT kind,id FROM documents ORDER BY kind,id")]
        result = {"format": FORMAT, "semantic_id": semantic_id, "profile": PROFILE,
                  "target": target, "domain": domain, "representations": rows,
                  "known_implementations": known,
                  "unbound_implementation_ids": [item["id"] for item in known if not item["representation_ids"]],
                  "snapshot_sha256": digest(snapshot_ids),
                  "query_sha256": digest({"semantic_id": semantic_id, "target": target, "domain": domain}),
                  "next_action": action, "execution_authorized": False,
                  "absence_established": False,
                  "scope": "local declarative planning; no equivalence, availability, rights or execution qualification"}
        if semantic_id in groups:
            group = groups[semantic_id]
            result["contract"] = {key: deepcopy(group[key]) for key in ("function", "constants", "effects")}
        return result

    def generate_swede_task(self, semantic_id, target, *, domain, reason, candidate_exclusions):
        """Explicit author/host request for another backing; exclusions remain claims."""
        _text(reason, "swede reason", 1024)
        _domain(domain)
        result = self.query(semantic_id, target, domain=domain)
        if "contract" not in result:
            raise ValueError("a swede task requires a known validated contract")
        if type(candidate_exclusions) is not list or len(candidate_exclusions) > 256:
            raise ValueError("bounded declared candidate exclusions required")
        known = {item["id"] for item in result["known_implementations"]}
        representations = {item["id"]: item["implementation"] for item in result["representations"]}
        exclusions, seen = [], set()
        for exclusion in candidate_exclusions:
            _fields(exclusion, ("implementation", "reason"), ("representation",))
            if _identifier(exclusion["implementation"], "implementation") not in known:
                raise ValueError("exclusion refers to an unknown matching implementation")
            _text(exclusion["reason"], "exclusion reason", 1024)
            representation = exclusion.get("representation")
            if representation is not None:
                _identifier(representation, "representation-study")
            if representation is not None and representations.get(representation) != exclusion["implementation"]:
                raise ValueError("exclusion representation does not belong to its implementation")
            key = (exclusion["implementation"], representation or "")
            if key in seen:
                raise ValueError("duplicate candidate exclusion")
            seen.add(key)
            exclusions.append({**deepcopy(exclusion), "assessment_status": "caller-declared"})
        task = {"format": "udc-registry-task-study-1", "kind": "swede", "reason": reason,
                "semantic_id": semantic_id, "profile": PROFILE, "target": target, "domain": deepcopy(domain),
                "contract": result["contract"], "known_implementations": result["known_implementations"],
                "candidate_exclusions": sorted(exclusions, key=lambda item: (item["implementation"], item.get("representation", ""))),
                "query_sha256": result["query_sha256"], "snapshot_sha256": result["snapshot_sha256"],
                "absence_established": False, "execution_authorized": False,
                "requirements": ["Assess the retained alternatives; exclusions are caller declarations, not proof of incompatibility.",
                                 "Preserve the supplied model contract and declared domain.",
                                 "Record source/model, build and target-execution evidence separately.",
                                 "Register a new immutable representation; do not rewrite prior evidence.",
                                 "Keep local registration separate from distribution review."]}
        task["task_sha256"] = digest(task)
        return task
