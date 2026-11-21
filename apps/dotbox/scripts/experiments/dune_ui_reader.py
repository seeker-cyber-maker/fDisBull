"""Bounded, read-only UI witnesses for one observed Dune DOS edition.

``describe(ram, ds=DS)`` consumes a coherent frozen 640 KiB conventional-RAM
image starting at linear address zero. It has no emulator, filesystem, network,
input, restore or disassembler dependency, and changes neither RAM nor state.
``describe_sparse(read, ds=DS)`` returns the same observation using a synchronous
``read(linear_address, length)`` callback, together with the raw control stability
witness and a receipt for every range actually read. The caller must keep the
guest at one coherent confirmed stop for the entire call. No cache survives it.

Entry conditions belong to the caller: verify SOURCE_SHA256/SOURCE_SIZE against
the actual executable and selected resources, CS=0824/DS=16F3 in real-mode,
16-bit, unpaged execution, and capture all bytes at one confirmed stopped
boundary. These bindings came from the supplied English RIP edition. This is
not an edition detector or a portable Dune adapter. A successful parse does not
verify those conditions, input ownership, readiness or rendered consistency.

CA45 selects loaded text through DS:4303/4307. Labels may be read without OCR;
phrase dictionary/control expansion is deliberately not implemented. The
A1F7 buffer and 42F5 box descriptor are candidate dialogue evidence, not proof
of a currently displayed line or a committed story effect. Buffer contents can
survive their presentation. In particular, a newer native frame ID alone does
not prove that captured pixels agree with logical state after a restore.

The admission digest covers only the reported menu/control context, excluding
hover highlighting. It is not a complete game-state token or a live-input grant.
The separate dialogue digest can detect unchanged measured dialogue witnesses;
a change does not establish story progress. ``compact(describe(ram))`` produces
a small inspection packet, with candidate text still explicitly unqualified.
Keep original RAM, decoded commercial text and captures outside the repository;
public tests use authored synthetic bytes only.
"""
from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Callable
from copy import deepcopy


SOURCE_SHA256 = "32439602abe95e0ff778653ad58052bfed56a73e103b92f079455daa2ee886e7"
SOURCE_SIZE = 74757
CS, DS = 0x0824, 0x16F3
RAM_BYTES, SEGMENT_BYTES = 0xA0000, 0x10000
MAX_CONTROLS, MAX_LABEL_BYTES, TEXT_WINDOW_BYTES = 64, 1024, 400
MAX_MAP_POINTS, MAX_SITE_RECORDS = 40, 128
ROW_CALLBACKS = (0xCE85, 0xCE80, 0xCE7B, 0xCE76, 0xCE71)
# Coalesce nearby dependencies to save RPCs as well as bytes. The first range
# includes bounded site records, controls, menus and current text-pool pointers.
# Unusual but valid menu/text pointers are still read on demand, never padded.
SPARSE_CORE_RANGE = (0x0004, 0x431D - 0x0004)
SPARSE_PAGING_RANGE = (0xFED4, 5)
SPARSE_TEXT_RANGE = (0xA107, MAX_MAP_POINTS * 6 + TEXT_WINDOW_BYTES)
SPARSE_POOL_BYTES = 4096
SPARSE_MAX_BYTES, SPARSE_MAX_READS = 128 * 1024, 256


class SnapshotError(ValueError):
    """The supplied snapshot does not satisfy the bounded observed schema."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ascii(payload: bytes) -> str:
    """Retain unexpanded controls visibly; do not silently join their text."""
    return "".join("\n" if value == 13 else chr(value) if 32 <= value <= 126
                   else f"\\x{value:02x}" for value in payload)


def _controls_in(payload: bytes) -> list[int]:
    return sorted({value for value in payload if value != 13 and not 32 <= value <= 126})


def _binding(ds: int) -> None:
    if type(ds) is not int or ds != DS:
        raise SnapshotError("The observed data-segment binding must remain 16F3")


def _range(address: int, count: int) -> None:
    if (type(address) is not int or type(count) is not int or count < 0
            or not 0 <= address <= RAM_BYTES - count):
        raise SnapshotError(f"Snapshot does not cover {address!r}+{count!r}")


def _merged_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for address, length in sorted(ranges):
        if not length:
            continue
        end = address + length
        if merged and address <= merged[-1][0] + merged[-1][1]:
            start, count = merged[-1]
            merged[-1] = (start, max(start + count, end) - start)
        else:
            merged.append((address, length))
    return merged


def _ranges_sha(blocks: list[tuple[int, bytes]]) -> str:
    digest = hashlib.sha256(b"dune-sparse-ranges-1\0")
    for address, block in blocks:
        digest.update(struct.pack("<II", address, len(block)))
        digest.update(block)
    return digest.hexdigest()


class _SparseMemory:
    """One observation's real returned ranges; an absent byte stays absent."""

    def __init__(self, read: Callable[[int, int], bytes]):
        if not callable(read):
            raise SnapshotError("Sparse memory needs a callable read(address, length)")
        self._read = read
        self._blocks: list[tuple[int, bytes]] = []
        self._dependencies: list[tuple[int, int]] = []
        self._receipts: list[dict] = []
        self._bytes = 0

    def _fetch(self, address: int, count: int) -> bytes:
        _range(address, count)
        if (self._bytes + count > SPARSE_MAX_BYTES
                or len(self._receipts) >= SPARSE_MAX_READS):
            raise SnapshotError("Sparse memory read budget exceeded")
        block = self._read(address, count)
        if not isinstance(block, (bytes, bytearray)) or len(block) != count:
            raise SnapshotError(f"Sparse read at {address:05X} must return exactly {count} bytes")
        block = bytes(block)
        self._blocks.append((address, block))
        self._bytes += count
        self._receipts.append({"address": address, "length": count, "sha256": _sha(block)})
        return block

    def __call__(self, address: int, count: int) -> bytes:
        self._dependencies.append((address, count))
        return self.prefetch(address, count)

    def prefetch(self, address: int, count: int) -> bytes:
        _range(address, count)
        cursor, end, pieces = address, address + count, []
        # Existing blocks never overlap: only gaps in their actual coverage
        # reach the callback. A failed/short read is never installed in cache.
        for start, block in sorted(self._blocks):
            stop = start + len(block)
            if stop <= cursor:
                continue
            if start >= end:
                break
            if start > cursor:
                pieces.append(self._fetch(cursor, start - cursor))
                cursor = start
            stop = min(stop, end)
            pieces.append(block[cursor - start:stop - start])
            cursor = stop
            if cursor == end:
                break
        if cursor < end:
            pieces.append(self._fetch(cursor, end - cursor))
        return b"".join(pieces)

    def prepare_pool(self, segment: int, offset: int) -> None:
        address = segment * 16 + offset
        count = min(SPARSE_POOL_BYTES, SEGMENT_BYTES - offset, RAM_BYTES - address)
        if count > 0:
            self.prefetch(address, count)

    def report(self) -> dict:
        return {"ranges": list(self._receipts), "calls": len(self._receipts), "bytes": self._bytes}

    def capture(self) -> dict:
        """Retain actual bytes and exact parser requests, excluding prefetch gaps."""
        def cached(address: int, length: int) -> bytes:
            end = address + length
            block = b"".join(data[max(address, start) - start:min(end, start + len(data)) - start]
                             for start, data in sorted(self._blocks)
                             if start < end and start + len(data) > address)
            if len(block) != length:
                raise SnapshotError("Sparse capture is missing a requested dependency")
            return block

        ranges = _merged_ranges([(address, len(block)) for address, block in self._blocks])
        blocks = [(address, cached(address, length)) for address, length in ranges]
        dependencies = _merged_ranges(self._dependencies)
        dependency_blocks = [(address, cached(address, length)) for address, length in dependencies]
        return {"schema": "dune-sparse-memory-1",
                "ranges": [{"address": address, "data_hex": block.hex()} for address, block in blocks],
                "dependencies": [{"address": address, "length": length} for address, length in dependencies],
                "sha256": _ranges_sha(blocks), "dependency_sha256": _ranges_sha(dependency_blocks)}


def describe(ram: bytes, *, ds: int = DS) -> dict:
    """Return bounded observations; raise SnapshotError on unsupported layout.

    ``bytes`` and ``bytearray`` are accepted, with a private immutable copy for
    the latter. The exact RAM extent and observed DS are deliberate scope
    checks. Rebinding another load mapping needs separate qualification.
    """
    if not isinstance(ram, (bytes, bytearray)) or len(ram) != RAM_BYTES:
        raise SnapshotError("Expected exactly 640 KiB of conventional RAM from linear zero")
    _binding(ds)
    ram = bytes(ram)

    def data(address: int, count: int) -> bytes:
        _range(address, count)
        return ram[address:address + count]

    return _describe(data, ds=ds)


def _sparse(read: Callable[[int, int], bytes], ds: int, *, text: bool) -> _SparseMemory:
    _binding(ds)
    memory = _SparseMemory(read)
    ranges = (SPARSE_CORE_RANGE, SPARSE_PAGING_RANGE)
    if text:
        ranges += (SPARSE_TEXT_RANGE,)
    for offset, length in ranges:
        memory.prefetch(ds * 16 + offset, length)
    return memory


def describe_sparse(read: Callable[[int, int], bytes], *, ds: int = DS) -> dict:
    """Read one coherent stopped UI without a full conventional-RAM transfer.

    ``read`` must return exactly the requested bytes or raise; callback errors
    propagate. The caller owns stopping, mapping checks and before/after stop
    revision checks. Neither a read receipt nor a successful parse grants input
    readiness or proves that pixels agree with the state. Returned ``reads``
    lists the actual callback ranges, their hashes, call count and total bytes;
    it is not a full-RAM hash or a restorable snapshot. ``structure_witness``
    retains the raw paging entries used by the controller's stability check.
    ``capture`` retains real returned ranges for private evidence. Its separate
    dependency digest binds only merged parser/structure requests, excluding
    unused prefetched bytes. All hashes are observation identities, not proof
    of admission, freshness or complete game-state equality.
    """
    memory = _sparse(read, ds, text=True)
    observation = _describe(memory, ds=ds, prepare_pool=memory.prepare_pool)
    structure = _structure(memory, ds=ds)
    return {"observation": observation, "structure_witness": structure,
            "reads": memory.report(), "capture": memory.capture()}


def read_structure_sparse(read: Callable[[int, int], bytes], *, ds: int = DS) -> dict:
    """Read the existing raw control-stability witness at one stopped boundary.

    This intentionally omits text, map-point and site-name decoding. Equality
    is the same narrow stability witness as the controller's full-DS check;
    it is not complete state equality, readiness or an input admission token.
    """
    memory = _sparse(read, ds, text=False)
    return {"structure_witness": _structure(memory, ds=ds),
            "reads": memory.report(), "capture": memory.capture()}


def _structure(data: Callable[[int, int], bytes], *, ds: int) -> dict:
    def segment(offset: int, count: int) -> bytes:
        if not 0 <= offset <= SEGMENT_BYTES - count:
            raise SnapshotError("Control witness read would wrap its 16-bit segment")
        return data(ds * 16 + offset, count)

    def word(offset: int) -> int:
        return struct.unpack("<H", segment(offset, 2))[0]

    count, rows = word(0x2184), segment(0xFED8, 1)[0]
    if not 1 <= count <= MAX_CONTROLS or rows > 5:
        raise SnapshotError("Control/row count leaves the bounded edition schema")
    controls = []
    for index in range(count):
        offset = 0x2186 + index * 14
        values = struct.unpack("<4H2B2H", segment(offset, 14))
        controls.append([offset, *values[:4], bool(values[4] & 0x80), values[7]])
    slot = word(0x2840)
    menu = word(slot)
    if menu > SEGMENT_BYTES - 2:
        raise SnapshotError("Menu header leaves the data segment")
    skip = struct.unpack("<b", segment(menu + 1, 1))[0]
    entries = [[word(menu + 2 + skip + 4 * row), word(menu + 4 + skip + 4 * row)]
               for row in range(rows)]
    return {"controls": controls, "slot": slot, "menu": menu, "skip": skip,
            "entries": entries, "rows": rows, "special": list(segment(0xFED4, 2)),
            "location": [word(4), word(6)], "ui_mode": segment(0x4247, 1)[0],
            "subject": word(0x431B),
            "dialogue": [word(0x4311), word(0x4315), segment(0x4319, 1)[0]] if menu == 0x2608 else None}


def _describe(data: Callable[[int, int], bytes], *, ds: int,
              prepare_pool: Callable[[int, int], None] | None = None) -> dict:
    def segmented(segment: int, offset: int, count: int) -> bytes:
        if not 0 <= offset <= SEGMENT_BYTES - count:
            raise SnapshotError("Read would wrap its 16-bit segment")
        return data(segment * 16 + offset, count)

    def byte(offset: int) -> int:
        return segmented(ds, offset, 1)[0]

    def word(offset: int) -> int:
        return struct.unpack("<H", segmented(ds, offset, 2))[0]

    def far(offset: int) -> dict:
        return {"offset": word(offset), "segment": word(offset + 2)}

    def text_lookup(text_id: int) -> dict:
        if not 1 <= text_id <= 0x3FFF:
            raise SnapshotError("Text id is outside the observed metadata range")
        index = text_id - 1
        slot = 0x4307 if index & 0x0800 else 0x4303
        if slot == 0x4307:
            index &= 0x07FF
        table = far(slot)
        table_entry = table["offset"] + index * 2
        if prepare_pool is not None:
            prepare_pool(table["segment"], table["offset"])
        pointer = struct.unpack("<H", segmented(table["segment"], table_entry, 2))[0]
        start = table["segment"] * 16 + pointer
        limit = min(MAX_LABEL_BYTES, SEGMENT_BYTES - pointer, RAM_BYTES - start)
        if limit <= 0:
            raise SnapshotError("Text pointer is outside captured conventional RAM")
        block = segmented(table["segment"], pointer, limit)
        terminator = block.find(b"\xff")
        if terminator < 0:
            raise SnapshotError("Text has no FF terminator in the bounded window")
        payload = block[:terminator]
        controls = _controls_in(payload)
        return {"text_id": text_id, "table_slot": slot, "table": table,
                "string_offset": pointer, "ascii": _ascii(payload),
                "ascii_only": not controls, "unexpanded_control_bytes": controls,
                "lookup_kind": "phrase_candidate" if slot == 0x4307 else "normal_label",
                "bytes_sha256": _sha(payload)}

    # D326 dispatches 14-byte control records; CE85..CE71 select command rows.
    count = word(0x2184)
    if not 1 <= count <= MAX_CONTROLS:
        raise SnapshotError("Control table count outside bounded schema")
    controls = []
    for index in range(count):
        offset = 0x2186 + index * 14
        x0, y0, x1, y1, flags0, flags1, value, callback = struct.unpack(
            "<4H2B2H", segmented(ds, offset, 14))
        active = bool(flags0 & 0x80)
        if active and not (0 <= x0 < x1 <= 320 and 0 <= y0 < y1 <= 200):
            raise SnapshotError("Active control has unsupported 320-by-200 geometry")
        controls.append({"record_offset": offset, "bounds": [x0, y0, x1, y1],
                         "flags": [flags0, flags1], "active": active,
                         "value": value, "callback": callback})
    by_offset = {control["record_offset"]: control for control in controls}

    # CE96 resolves menu entries. CECC renders metadata&3FFF; bit4000 rejects
    # the action while bit8000 only changes highlighting.
    stack_slot = word(0x2840)
    menu = word(stack_slot)
    segmented(ds, menu, 2)
    skip = struct.unpack("<b", segmented(ds, menu + 1, 1))[0]
    first = menu + 2 + skip
    special_row, mode = byte(0xFED5), byte(0xFED4)
    count_visible = byte(0xFED8)
    if count_visible > 5:
        raise SnapshotError("Visible row count exceeds the five-row renderer")
    if special_row != 0xFF and special_row >= 5:
        raise SnapshotError("Paging row is outside the five-row renderer")
    segmented(ds, first, 4 * count_visible)
    rows = []
    for index in range(count_visible):
        entry = first + 4 * index
        if index == special_row:
            metadata = 0x0094
            handler = 0xCE65 if mode & 0x80 else 0xCE6B if mode else 0
            source = "generated_paging_row"
        else:
            metadata, handler = word(entry), word(entry + 2)
            source = "menu_record"
        label_id = metadata & 0x3FFF
        if not label_id:
            raise SnapshotError("Visible menu row has no label id")
        record_offset = 0x21E8 + 14 * index
        control = by_offset.get(record_offset)
        if control is None or control["callback"] != ROW_CALLBACKS[index]:
            raise SnapshotError("Expected command rectangle/callback absent")
        rows.append({"row": index, "source": source, "entry_offset": entry,
                     "record_offset": record_offset, "metadata": metadata,
                     "handler": handler, "disabled_by_metadata": bool(metadata & 0x4000),
                     "highlighted": bool(metadata & 0x8000),
                     "active_rectangle": control["active"], "bounds": control["bounds"],
                     "callback": control["callback"], "label": text_lookup(label_id)})

    # 9583 / A7AE assemble text into A1F7 before 96E3 renders it. 9875 clears
    # the active box descriptor, but need not clear the retained text buffer.
    buffer = segmented(ds, 0xA1F7, TEXT_WINDOW_BYTES)
    end = next((i for i, value in enumerate(buffer) if value >= 0xF0), None)
    empty = not any(buffer)
    payload = b"" if empty else buffer if end is None else buffer[:end]
    box_descriptor = word(0x42F5)
    speech = {"buffer_offset": 0xA1F7, "window_bytes": TEXT_WINDOW_BYTES,
              "terminator_offset": end, "terminator": None if end is None else buffer[end],
              "ascii_projection": _ascii(payload),
              "nonprintable_bytes": _controls_in(payload),
              "window_sha256": _sha(buffer),
              "buffer_status": "zero_filled" if empty else "terminated_candidate" if end is not None
                               else "unterminated_candidate",
              "text_box_word_42f5": box_descriptor,
              "remaining_text_pointer": far(0x430D),
              "context": {"box_descriptor": box_descriptor,
                          "box_descriptor_nonzero": box_descriptor != 0,
                          "menu_is_conversation": menu == 0x2608,
                          "rendered_currentness": "unqualified"},
              "freshness": "Candidate buffer; qualify against a current visible line or text-display boundary"}

    # 9E91 writes subject; 9EBD initializes selector=subject*8. 9F3F consumes
    # record/selector/mask on the conversation action. Their story meaning is
    # deliberately opaque, including the two bitsets updated upon entry.
    location = {"word_0004": word(4), "word_0006": word(6)}
    subject = word(0x431B)
    conversation = {
        "menu_is_2608": menu == 0x2608,
        "subject_selector_431b": subject,
        "dialogue_record_4311": word(0x4311),
        "dialogue_selector_4315": word(0x4315),
        "dialogue_mask_4319": byte(0x4319),
        "subject_record_42f9": word(0x42F9),
        "entry_bitset_000e": word(0x000E),
        "entry_bitset_0014": word(0x0014),
    }
    # 9D32 checks2608 as conversation context. Subject0 alone is insufficient:
    # that value also exists outside a conversation in the observed baseline.
    if menu == 0x2608 and subject < 0x17:
        conversation["subject_name_candidate"] = text_lookup(subject + 0x6E)

    def site_name(pointer: int) -> dict | None:
        if pointer == 0:
            return None
        # 6B6E walks 1C-byte site records from0100. A negative 4258 value
        # can instead represent a desert direction; do not dereference it.
        if not (0x0100 <= pointer < 0x0100 + MAX_SITE_RECORDS * 0x1C
                and (pointer - 0x0100) % 0x1C == 0) or word(pointer) == 0xFFFF:
            return {"record_offset": pointer, "name_candidate": None,
                    "qualification": "unrecognized_or_direction_pointer"}
        # 7046 renders the two name components and chooses its separator.
        first_id, second_part = byte(pointer), byte(pointer + 1)
        if first_id == 0:
            return {"record_offset": pointer, "name_candidate": None,
                    "qualification": "unnamed_record"}
        first_name, second_name = text_lookup(first_id), text_lookup(second_part + 0x0C)
        separator = "-" if second_part >= 3 else " "
        return {"record_offset": pointer,
                "name_candidate": first_name["ascii"] + separator + second_name["ascii"],
                "name_ascii_only": first_name["ascii_only"] and second_name["ascii_only"],
                "name_text_ids": [first_id, second_part + 0x0C],
                "type_byte_0008": byte(pointer + 8),
                "world_words": [word(pointer + 2), word(pointer + 4)],
                "qualification": "name_from_loaded_resource; location_and_arrival_require_context"}

    ui_mode = byte(0x4247)
    site = {"current_record_114e": word(0x114E), "selected_record_4258": word(0x4258),
            "site_location_context": (word(6) & 0xFF) == 0x80,
            "map_mode_4247": ui_mode, "map_points_context_active": ui_mode != 0,
            "current_name_candidate": site_name(word(0x114E)),
            "selected_name_candidate": site_name(word(0x4258)),
            "rendered_map_points": [],
            "scope": "Record identities and map selection are not arrival or travel completion"}
    if ui_mode != 0:
        # 6B6E produces six-byte screen entries atA107; 6C0D filters mode and
        # finds the nearest Manhattan point. 4D9F accepts distances below9.
        # A1F7 starts the text buffer, imposing this independent read bound.
        for index in range(MAX_MAP_POINTS):
            offset = 0xA107 + 6 * index
            pointer = word(offset)
            if pointer == 0:
                break
            x, packed = word(offset + 2), word(offset + 4)
            if packed >> 8 != ui_mode:
                continue
            y = packed & 0xFF
            if not (0 <= x < 320 and 0 <= y < 200):
                raise SnapshotError("Map point is outside the observed screen geometry")
            name = site_name(pointer)
            if name is None or name["name_candidate"] is None:
                raise SnapshotError("Map point does not identify a bounded named site record")
            site["rendered_map_points"].append({"entry_offset": offset,
                                                "site_record": pointer, "screen_xy": [x, y],
                                                "mode": packed >> 8, "site": name})
        else:
            raise SnapshotError("Map point table has no terminator before the text buffer")

    result = {"schema": "dune-frozen-ui-witness-1", "data_segment": ds,
              "location_key": location, "subject_selector_431b": subject,
              "ui_mode_4247": ui_mode,
              "menu": {"stack_slot": stack_slot, "menu_offset": menu,
                       "page_skip": skip, "paging_mode": mode, "special_row": special_row,
                       "visible_rows": count_visible, "rows": rows},
              "controls": controls, "text_buffer_candidate": speech,
              "conversation_witness": conversation, "site_witness": site}
    semantic_key = {"location": location, "menu": menu, "menu_stack_slot": stack_slot,
                    "page_skip": skip, "paging_mode": mode, "special_row": special_row,
                    "ui_mode": ui_mode,
                    "site": {key: site[key] for key in
                             ("current_record_114e", "selected_record_4258")},
                    "subject": subject,
                    "rows": [{"label": row["label"]["ascii"], "handler": row["handler"],
                              "disabled": row["disabled_by_metadata"], "active": row["active_rectangle"],
                              "bounds": row["bounds"], "record_offset": row["record_offset"],
                              "callback": row["callback"]} for row in rows],
                    "controls": [{key: control[key] for key in
                                  ("record_offset", "bounds", "active", "value", "callback")}
                                 for control in controls],
                    "map_points": [{key: point[key] for key in ("site_record", "screen_xy", "mode")}
                                   for point in site["rendered_map_points"]]}
    if menu == 0x2608:
        semantic_key["dialogue"] = {key: conversation[key] for key in
                                   ("dialogue_record_4311", "dialogue_selector_4315",
                                    "dialogue_mask_4319", "subject_record_42f9")}
    result["menu_admission_sha256"] = _sha(
        json.dumps(semantic_key, sort_keys=True, separators=(",", ":")).encode())
    # Ignore unused trailing buffer bytes and layout-only descriptor changes.
    # Repeated equal witnesses are useful to bound a continuation macro; the
    # digest is not a claim that different witnesses advanced the story.
    dialogue_key = {"menu": menu, "subject": subject,
                    "fields": {key: conversation[key] for key in
                               ("dialogue_record_4311", "dialogue_selector_4315",
                                "dialogue_mask_4319", "subject_record_42f9")},
                    "box_present": box_descriptor != 0,
                    "remaining_pointer": speech["remaining_text_pointer"],
                    "text_sha256": _sha(payload), "terminator": speech["terminator"]}
    result["dialogue_witness_sha256"] = _sha(
        json.dumps(dialogue_key, sort_keys=True, separators=(",", ":")).encode())
    return result


def compact(observation: dict) -> dict:
    """Project a describe() result for inspection, without narrating as current.

    An inactive conversation box, missing terminator or unexpanded controls
    withhold text from ``line_candidate``. Other map/status renderers can use
    the same buffer without that box; their presentation remains unqualified.
    Even a returned candidate still needs external visible/text-display
    qualification. Dispatch bits are narrower than live
    input readiness, ownership, effect success or a complete action guard.
    """
    speech = observation["text_buffer_candidate"]
    context = speech["context"]
    if not context["box_descriptor_nonzero"]:
        status = "conversation_box_inactive"
    elif speech["terminator"] is None or not speech["ascii_projection"]:
        status = "incomplete_or_empty_buffer"
    elif speech["nonprintable_bytes"]:
        status = "unexpanded_controls"
    else:
        status = "candidate_line"
    name = observation["conversation_witness"].get("subject_name_candidate")
    return {
        "location_key": observation["location_key"],
        "menu_offset": observation["menu"]["menu_offset"],
        "subject_selector": observation["subject_selector_431b"],
        "subject_name_candidate": name["ascii"] if name and name["ascii_only"] else None,
        "choices": [{"row": row["row"], "label": row["label"]["ascii"],
                     "label_ascii_only": row["label"]["ascii_only"],
                     "record_offset": row["record_offset"], "handler": row["handler"],
                     "row_flags_allow_dispatch": row["active_rectangle"]
                     and not row["disabled_by_metadata"] and row["handler"] != 0}
                    for row in observation["menu"]["rows"]],
        "dialogue": {"status": status,
                     "line_candidate": speech["ascii_projection"] if status == "candidate_line" else None,
                     "box_descriptor": context["box_descriptor"],
                     "rendered_currentness": "unqualified",
                     "other_presentations": "map/status presentation unqualified"},
        "sites": observation["site_witness"],
        "menu_admission_sha256": observation["menu_admission_sha256"],
        "dialogue_witness_sha256": observation["dialogue_witness_sha256"],
    }


def changed_compact(before: dict | None, after: dict) -> dict:
    """Return a complete initial compact packet or complete changed fields.

    Both hashes cover the entire corresponding ``compact`` packet, serialized
    with JSON sorted keys, compact separators and the default ASCII escaping.
    A consumer applies a delta only to a cached packet matching ``base_sha256``,
    replaces each listed top-level field, then checks ``current_sha256`` against
    the complete result. An initial ``full`` packet replaces the whole cache.
    Empty delta fields mean equal compact observations, not a fresh input grant.

    This carries compact's candidate-only presentation semantics. It neither
    exposes raw witnesses nor creates admission tokens; the controller must
    separately supply any newly qualified token at its actual input boundary.
    """
    current = deepcopy(compact(after))
    previous = None if before is None else compact(before)

    def digest(packet: dict) -> str:
        return _sha(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode())

    return {"schema": "dune-compact-delta-1", "kind": "full" if before is None else "delta",
            "base_sha256": None if previous is None else digest(previous),
            "current_sha256": digest(current),
            "fields": current if previous is None else
                      {key: value for key, value in current.items() if previous[key] != value}}
