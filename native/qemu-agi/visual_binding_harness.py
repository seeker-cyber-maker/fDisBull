"""Owned harness for the explicit catalog-backed AGI view-binding profile.

The existing QMP transport owns the child and its finite command deadlines.
This adapter supplies one immutable caller-authored binary catalog, selects the
separate machine profile, and checks code/catalog identity on every observation.
It does not discover a binary, load game resources, interpret AGI, or render.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

from harness import HarnessError, QemuAGI


VIEW_BINDING_PROFILE = "agi-2917-view-binding-pilot-1"
STATE_SCHEMA = "fdisbull-agi-binding-state-1"
EVENTS_SCHEMA = "fdisbull-agi-binding-events-1"


def binding_guest_state(state):
    """Copy every architectural field for complete mask-neutrality comparison."""
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA \
            or not isinstance(state.get("guest"), dict):
        raise HarnessError("Unsupported AGI binding state schema")
    return deepcopy(state["guest"])


class QemuAGIViewBinding(QemuAGI):
    """Run an explicit ``view-catalog`` profile using the existing owned child.

    ``catalog`` contains exact FDBAGIV1 bytes (1..65536 bytes). Native startup
    performs the structural admission; this wrapper intentionally does not
    implement a second catalog parser. The catalog path is caller-readable for
    auditing, but file changes after startup cannot change the admitted native
    catalog or its bound identity. Restart preserves that native catalog.

    The ordinary configure/run/state/events/restart/clear_events/get/set APIs
    retain QemuAGI's bounds and stopped-state requirements. An explicit runtime
    with a different profile or source identity fails instead of falling back.
    """

    profile = VIEW_BINDING_PROFILE
    state_schema = STATE_SCHEMA
    events_schema = EVENTS_SCHEMA
    machine_properties = ()

    def __init__(self, binary, code, catalog, *, timeout=10.0, extra_args=(),
                 evidence_dir=None, transport="stdio"):
        if type(catalog) is not bytes or not 1 <= len(catalog) <= 65536:
            raise ValueError("An explicit 1..65536-byte binary VIEW catalog is required")
        if not isinstance(extra_args, (list, tuple)) \
                or any(not isinstance(arg, str) for arg in extra_args):
            raise ValueError("extra_args must be a sequence of command arguments")
        self.catalog_bytes = catalog
        self.catalog_sha256 = hashlib.sha256(catalog).hexdigest()
        self.catalog_size = len(catalog)
        self._catalog_temporary = tempfile.TemporaryDirectory(prefix="fdb-agi-view-")
        self.catalog_path = Path(self._catalog_temporary.name) / "views.fdbagiv1"
        try:
            self.catalog_path.write_bytes(catalog)
            # QEMU merges this explicit property into the existing agi-test
            # machine selection. The returned schema/profile is checked below.
            super().__init__(
                binary, code, timeout=timeout,
                extra_args=("-M", ",".join(("agi-test", f"view-catalog={self.catalog_path}",
                                           *self.machine_properties)), *extra_args),
                evidence_dir=evidence_dir, transport=transport,
            )
            self.code_size = len(code)
            self.state()
        except BaseException:
            if getattr(self, "_temporary", None) is not None:
                self.close(failed=True)
            elif self._catalog_temporary is not None:
                self._catalog_temporary.cleanup()
                self._catalog_temporary = None
            raise

    @property
    def expected_source(self):
        return {"sha256": self.source_sha256, "size": self.code_size,
                "logic_id": 0, "profile": self.profile,
                "catalog_sha256": self.catalog_sha256}

    def state(self):
        state = super().state()
        if state.get("schema") != self.state_schema or state.get("source") != self.expected_source:
            raise HarnessError("AGI binding state profile or source identity differs")
        catalog = state.get("catalog")
        if not isinstance(catalog, dict) or catalog.get("sha256") != self.catalog_sha256 \
                or catalog.get("size") != self.catalog_size:
            raise HarnessError("AGI binding catalog identity differs")
        return state

    def events(self):
        events = self._json_property("agi-events-json")
        if not isinstance(events, dict) or events.get("schema") != self.events_schema \
                or events.get("source") != self.expected_source \
                or not isinstance(events.get("events"), list):
            raise HarnessError("Unsupported AGI binding events or source identity")
        return events

    def close(self, *, failed=False):
        try:
            super().close(failed=failed)
            if failed and self.failure_evidence is not None:
                # Preserve the exact admitted input, not a subsequently changed
                # file. This adds at most 64 KiB to the existing bounded log.
                (self.failure_evidence / "view-catalog.bin").write_bytes(self.catalog_bytes)
                (self.failure_evidence / "view-catalog.json").write_text(json.dumps({
                    "sha256": self.catalog_sha256, "bytes": self.catalog_size,
                    "profile": self.profile,
                }, indent=2) + "\n", encoding="utf-8")
        finally:
            if self._catalog_temporary is not None:
                self._catalog_temporary.cleanup()
                self._catalog_temporary = None
