"""Read-only DOS views over canonical physical addresses and CS-specific facts.

Global annotations/representations identify physical entries. Instructions and
control-flow interpretations retain the CS under which their IP was decoded.
No query here decodes new bytes or upgrades segment candidates to known code.
"""
from __future__ import annotations

import json
import re

_CONTEXT = re.compile(r"^x86:16:little:cs=([0-9a-fA-F]{4})$")
_SEGMENTED = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,4}):(?:0x)?([0-9a-fA-F]{1,4})$")
_BASE_CONTEXT = "x86:16:little"


def _key(address):
    return f"{address:016x}"


def _hex(address):
    return f"0x{address:x}"


def _bounded(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _selector(value):
    if isinstance(value, str):
        if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,4}", value):
            raise ValueError("cs must be a 16-bit hexadecimal segment selector")
        value = int(value, 16)
    return _bounded(value, "cs", 0, 0xFFFF)


def _context(selector):
    return f"{_BASE_CONTEXT}:cs={selector:04x}"


def _context_selector(context):
    match = _CONTEXT.fullmatch(context or "")
    return int(match[1], 16) if match else None


def _segmented(address, context):
    selector = _context_selector(context)
    offset = address - selector * 16 if selector is not None else None
    return f"{selector:04x}:{offset:04x}" if offset is not None and 0 <= offset <= 0xFFFF else None


class DOSViewsMixin:
    def _dos_parse_address(self, value, cs=None):
        """Return linear address and an explicitly supplied CS, if any.

        CS:IP strings use hexadecimal fields. Plain addresses follow the common
        decimal/0x API convention. This validates real-mode ranges, not whether
        the address belongs to a mapped module or a discovered segment.
        """
        selector = _selector(cs) if cs is not None else None
        if isinstance(value, str) and ":" in value:
            match = _SEGMENTED.fullmatch(value.strip())
            if not match:
                raise ValueError("DOS segmented address must have 16-bit hexadecimal CS:IP fields")
            supplied, offset = int(match[1], 16), int(match[2], 16)
            if selector is not None and selector != supplied:
                raise ValueError("cs conflicts with the segment in CS:IP")
            selector = supplied
            linear = supplied * 16 + offset
        else:
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError("DOS address must be an integer, integer string, or CS:IP")
            try:
                linear = int(value, 0) if isinstance(value, str) else value
            except ValueError as exc:
                raise ValueError("DOS address must be an integer string or CS:IP") from exc
        if not 0 <= linear < 0x100000:
            raise ValueError("DOS linear address must fit below 1 MiB; A20 wrapping is not supported")
        if selector is not None and not 0 <= linear - selector * 16 <= 0xFFFF:
            raise ValueError("DOS linear address does not fit the selected CS:IP window")
        return linear, selector

    def _dos_label(self, v, a, context=None):
        row = self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",
                              (v, _BASE_CONTEXT, _key(a))).fetchone()
        if row:
            return row[0]
        row = None
        if context is not None:
            row = self.db.execute("SELECT name FROM functions WHERE version=? AND context=? AND address=?",
                                  (v, context, _key(a))).fetchone()
        if row is None:
            row = self.db.execute("SELECT name FROM functions WHERE version=? AND address=? ORDER BY context,name LIMIT 1",
                                  (v, _key(a))).fetchone()
        if row:
            return row[0]
        segmented = _segmented(a, context)
        return "loc_" + segmented.replace(":", "_") if segmented else f"mem_{a:x}"

    def _dos_presentation(self, v, a, context=None):
        row = self.db.execute("SELECT representation,size FROM definitions WHERE version=? AND context=? AND address=?",
                              (v, _BASE_CONTEXT, _key(a))).fetchone()
        if row is None:
            row = self.db.execute("SELECT representation,size FROM data_items WHERE version=? AND context=? AND address=?",
                                  (v, _BASE_CONTEXT, _key(a))).fetchone()
        if row is None:
            if context is not None:
                instruction = self.db.execute("SELECT size FROM instructions WHERE version=? AND context=? AND address=?",
                                              (v, context, _key(a))).fetchone()
            else:
                instruction = self.db.execute("SELECT size FROM instructions WHERE version=? AND address=? ORDER BY context LIMIT 1",
                                              (v, _key(a))).fetchone()
            if instruction:
                row = ("code", instruction[0])
        return {"name": self._dos_label(v, a, context), "representation": row[0] if row else None,
                "size": row[1] if row else None}

    def _dos_functions(self, version=None, limit=200, offset=0):
        limit = _bounded(limit, "limit", 1, 10000)
        offset = _bounded(offset, "offset", 0, (1 << 63) - 1)
        with self.transaction():
            v = self.version(version)["id"]
            rows = self.db.execute("SELECT * FROM functions WHERE version=? AND context LIKE ? ORDER BY address,context LIMIT ? OFFSET ?",
                                   (v, _BASE_CONTEXT + ":cs=%", limit, offset)).fetchall()
            return [{"address": _hex(int(row["address"], 16)),
                     "name": self._dos_label(v, int(row["address"], 16), row["context"]),
                     "source": row["source"], "status": row["status"], "version": v,
                     "context": row["context"], "cs": _context_selector(row["context"]),
                     "ip": int(row["address"], 16) - _context_selector(row["context"]) * 16,
                     "segmented_address": _segmented(int(row["address"], 16), row["context"])} for row in rows]

    def _dos_xrefs(self, address, direction="to", version=None, limit=200, cs=None):
        if direction not in ("to", "from"):
            raise ValueError("direction must be to or from")
        limit = _bounded(limit, "limit", 1, 10000)
        a, selector = self._dos_parse_address(address, cs)
        selected = _context(selector) if selector is not None else None
        with self.transaction():
            v = self.version(version)["id"]
            column = "target" if direction == "to" else "source"
            edges = self.db.execute(f"SELECT * FROM dos_edges WHERE version=? AND {column}=? ORDER BY source,source_context,target,target_context,kind LIMIT ?",
                                    (v, _key(a), 10000)).fetchall()
            records, edge_keys = [], set()
            for row in edges:
                source_context, target_context = row["source_context"], row["target_context"]
                edge_keys.add((source_context, row["source"], row["target"], row["kind"]))
                if selected is not None:
                    if direction == "from" and source_context != selected:
                        continue
                    if direction == "to" and target_context not in (None, "", _BASE_CONTEXT, selected):
                        continue
                records.append(dict(row))
            # Legacy/global xrefs carry source CS but may lack target-CS facts.
            # Keep those only when no richer dos_edge already represents them.
            for row in self.db.execute(f"SELECT * FROM xrefs WHERE version=? AND {column}=? ORDER BY source,context,target,kind LIMIT ?",
                                       (v, _key(a), 10000)):
                identity = (row["context"], row["source"], row["target"], row["kind"])
                if identity in edge_keys or (selected is not None and direction == "from" and row["context"] != selected):
                    continue
                records.append({"version": v, "source_context": row["context"], "source": row["source"],
                                "target": row["target"], "target_context": "", "kind": row["kind"], "evidence": row["evidence"]})
            records.sort(key=lambda row: (row["source"], row["source_context"], row["target"], row["target_context"] or "", row["kind"]))
            result = []
            for row in records[:limit]:
                source, target = int(row["source"], 16), int(row["target"], 16)
                source_context, target_context = row["source_context"], row["target_context"] or None
                result.append({"source": _hex(source), "target": _hex(target), "kind": row["kind"],
                               "evidence": row["evidence"], "version": v,
                               "context": source_context, "source_context": source_context, "target_context": target_context,
                               "source_cs": _context_selector(source_context), "target_cs": _context_selector(target_context),
                               "source_segmented_address": _segmented(source, source_context),
                               "target_segmented_address": _segmented(target, target_context),
                               "source_name": self._dos_label(v, source, source_context),
                               "target_name": self._dos_label(v, target, target_context),
                               "target_representation": self._dos_presentation(v, target, target_context)["representation"]})
            return result

    def _dos_disassembly(self, address=None, lines=50, version=None, cs=None):
        count = _bounded(lines, "lines", 1, 500)
        a, selector = self._dos_parse_address(self.meta["entry"] if address is None else address, cs)
        explicit = selector is not None
        with self.transaction():
            v = self.version(version)
            chosen_context = _context(selector) if explicit else None
            start = a
            warnings = []
            if chosen_context is None:
                neighbors = []
                for comparison, order in ((">=", "ASC"), ("<=", "DESC")):
                    row = self.db.execute(f"SELECT address,context FROM instructions WHERE version=? AND context LIKE ? AND address{comparison}? ORDER BY address {order},context LIMIT 1",
                                          (v["id"], _BASE_CONTEXT + ":cs=%", _key(a))).fetchone()
                    if row:
                        neighbors.append(row)
                if neighbors:
                    closest = min(neighbors, key=lambda row: (abs(int(row["address"], 16) - a), int(row["address"], 16), row["context"]))
                    start, chosen_context = int(closest["address"], 16), closest["context"]
                    if start != a:
                        warnings.append("Showing the nearest stored instruction address; no bytes were decoded by this query.")
            exact = self.db.execute("SELECT 1 FROM instructions WHERE version=? AND context=? AND address=?",
                                    (v["id"], chosen_context, _key(a))).fetchone() if explicit else True
            if explicit and not exact:
                warnings.append("No stored instruction starts at the requested address in the selected CS context; the exact-address view is empty and no bytes were decoded.")
            rows = self.db.execute("SELECT * FROM instructions WHERE version=? AND context=? AND address>=? ORDER BY address LIMIT ?",
                                   (v["id"], chosen_context, _key(start), count)).fetchall() if chosen_context and exact else []
            instructions, first_alternatives = [], []
            for row in rows:
                linear = int(row["address"], 16)
                row_cs = _context_selector(row["context"])
                segmented_address = _segmented(linear, row["context"])
                if segmented_address is None:
                    raise ValueError("stored DOS instruction is outside its CS:IP window")
                alternatives = [item[0] for item in self.db.execute("SELECT context FROM instructions WHERE version=? AND address=? AND context!=? ORDER BY context",
                                                                    (v["id"], row["address"], row["context"]))]
                if not instructions:
                    first_alternatives = alternatives
                if alternatives and not explicit and not any("aliases" in warning for warning in warnings):
                    warnings.append("Stored CS aliases exist at this physical address; the first context was selected deterministically. Supply cs or CS:IP to select another interpretation.")
                references = []
                for reference in self.db.execute("SELECT * FROM operand_refs WHERE version=? AND context=? AND source=? ORDER BY operand_index,role,target",
                                                 (v["id"], row["context"], row["address"])):
                    target = int(reference["target"], 16)
                    targets = [item[0] for item in self.db.execute("SELECT DISTINCT target_context FROM dos_edges WHERE version=? AND source_context=? AND source=? AND target=? ORDER BY target_context",
                                                                 (v["id"], row["context"], row["address"], reference["target"]))]
                    target_context = targets[0] if len(targets) == 1 and targets[0] else None
                    references.append({"operand_index": reference["operand_index"], "role": reference["role"],
                                       "target": _hex(target), "width": reference["width"], "target_context": target_context,
                                       "segmented_address": _segmented(target, target_context),
                                       **self._dos_presentation(v["id"], target, target_context)})
                display = row["operands"]
                if references:
                    display += " ; " + ", ".join(item["name"] + (f" <{item['representation']}>" if item["representation"] else "") for item in references)
                comment = self.db.execute("SELECT text,author,inherited_from FROM annotations WHERE version=? AND context=? AND address=? AND kind='comment'",
                                          (v["id"], _BASE_CONTEXT, row["address"])).fetchone()
                state = self.db.execute("SELECT registers,state,reason FROM dos_states WHERE version=? AND context=? AND address=?",
                                        (v["id"], row["context"], row["address"])).fetchone()
                has_label = self.db.execute("SELECT 1 FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",
                                            (v["id"], _BASE_CONTEXT, row["address"])).fetchone() is not None
                if not has_label:
                    has_label = self.db.execute("SELECT 1 FROM functions WHERE version=? AND address=? LIMIT 1",
                                                (v["id"], row["address"])).fetchone() is not None
                display,file_refs,file_refs_summary=self._file_reference_display(v['id'],row['context'],linear,display)
                instructions.append({"address": _hex(linear), "cs": row_cs, "ip": linear - row_cs * 16,
                                     "segmented_address": segmented_address, "context": row["context"],
                                     "alternative_contexts": alternatives, "size": row["size"], "bytes": row["bytes"],
                                     "mnemonic": row["mnemonic"], "operands": row["operands"], "raw_operands": row["operands"],
                                     "display_operands": display, "file_references":file_refs, "file_reference_summary":file_refs_summary, "flow": row["flow"],
                                     "target": _hex(int(row["target"], 16)) if row["target"] is not None else None,
                                     "name": self._dos_label(v["id"], linear, row["context"]), "show_label": has_label, "references": references,
                                     "comment": comment[0] if comment else None, "comment_author": comment[1] if comment else None,
                                     "comment_inherited_from": comment[2] if comment else None,
                                     "xrefs": self._dos_xrefs(linear, "to", v["id"], cs=row_cs),
                                     "assumptions": {"registers": json.loads(state[0]), "state": state[1], "reason": state[2]} if state else None})
            return {"title": self.meta["filename"], "arch": self.arch, "bits": self.bits,
                    "version": v["id"], "sha256": v["sha256"], "source_sha256": self.meta["source_sha256"],
                    "context": chosen_context, "address": _hex(a), "view_start": _hex(start),
                    "alternative_contexts": first_alternatives, "instructions": instructions, "warnings": warnings,
                    "analysis": self.analysis_status(v['id']),
                    "view": "Stored static DOS instructions in one CS context; register assumptions and segment bounds are inferred, not runtime observations."}

    def _dos_segments(self, version=None):
        with self.transaction():
            v = self.version(version)["id"]
            result = []
            for row in self.db.execute("SELECT * FROM dos_segments WHERE version=? ORDER BY selector", (v,)):
                selector, context = row["selector"], _context(row["selector"])
                count = self.db.execute("SELECT count(*) FROM instructions WHERE version=? AND context=?", (v, context)).fetchone()[0]
                result.append({"version": v, "selector": selector, "segment": f"{selector:04x}", "context": context,
                               "base": _hex(int(row["base"], 16)), "end": _hex(int(row["end"], 16)),
                               "roles": json.loads(row["roles"]), "sources": json.loads(row["sources"]),
                               "instruction_count": count, "bounds_inferred": True,
                               "classification": "candidate segment; decoded code is reported separately"})
            return result

    def _dos_regions(self, version=None):
        """Report contiguous stored instruction runs independently for each CS."""
        with self.transaction():
            v = self.version(version)["id"]
            result, run = [], None
            for row in self.db.execute("SELECT context,address,size FROM instructions WHERE version=? AND context LIKE ? ORDER BY context,address",
                                       (v, _BASE_CONTEXT + ":cs=%")):
                address, context = int(row["address"], 16), row["context"]
                end = address + row["size"]
                if run is not None and run["context"] == context and run["_end"] == address:
                    run["_end"] = end
                    run["instruction_count"] += 1
                else:
                    run = {"version": v, "context": context, "cs": _context_selector(context),
                           "_start": address, "_end": end, "instruction_count": 1,
                           "classification": "decoded instruction run"}
                    result.append(run)
            for run in result:
                start, end = run.pop("_start"), run.pop("_end")
                run.update(start=_hex(start), end=_hex(end), start_segmented=_segmented(start, run["context"]),
                           end_segmented=_segmented(end, run["context"]), end_exclusive=True)
            return result
