"""Authored RAM verifies reader boundaries, not a commercial game's behavior."""
import importlib.util
import hashlib
import json
from pathlib import Path
import struct

import pytest


SPEC = importlib.util.spec_from_file_location(
    "dune_ui_reader", Path(__file__).resolve().parents[1] / "scripts/experiments/dune_ui_reader.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
BASE = reader.DS * 16
TEXT_SEGMENT, TEXT_TABLE = 0x3000, 0x0040


def put_word(ram, offset, value):
    struct.pack_into("<H", ram, BASE + offset, value)


def put_label(ram, text_id, payload, *, offset=0x0400, phrase=False):
    segment, table = (0x4000, 0x0030) if phrase else (TEXT_SEGMENT, TEXT_TABLE)
    index = (text_id - 1) & 0x07FF if phrase else text_id - 1
    struct.pack_into("<H", ram, segment * 16 + table + index * 2, offset)
    start = segment * 16 + offset
    ram[start:start + len(payload) + 1] = payload + b"\xff"


def authored_ram(*, conversation=False):
    ram = bytearray(reader.RAM_BYTES)
    put_word(ram, 0x2184, 12)
    for index in range(12):
        offset = 0x2186 + index * 14
        if 7 <= index <= 11:
            row = index - 7
            bounds, callback = (92, 159 + row * 8, 228, 167 + row * 8), reader.ROW_CALLBACKS[row]
        else:
            bounds, callback = (index * 8, 10, index * 8 + 6, 16), 0x1000 + index
        struct.pack_into("<4H2B2H", ram, BASE + offset, *bounds, 0x80, 0, 1, callback)
    menu = 0x2608 if conversation else 0x2598
    put_word(ram, 0x2840, 0x2824)
    put_word(ram, 0x2824, menu)
    put_word(ram, menu, 0x00FF)
    for index, text_id in enumerate((1, 2)):
        put_word(ram, menu + 2 + 4 * index, text_id)
        put_word(ram, menu + 4 + 4 * index, 0x1111 + index)
    ram[BASE + 0xFED5] = 0xFF
    ram[BASE + 0xFED8] = 2
    put_word(ram, 0x4303, TEXT_TABLE)
    put_word(ram, 0x4305, TEXT_SEGMENT)
    put_word(ram, 0x4307, 0x0030)
    put_word(ram, 0x4309, 0x4000)
    put_label(ram, 1, b"Authored alpha")
    put_label(ram, 2, b"Authored beta", offset=0x0440)
    put_label(ram, 0x94, b"Authored next page", offset=0x0480)
    put_label(ram, 0x6E, b"Authored speaker", offset=0x04C0)
    return ram


def put_speech(ram, payload, *, box=0x2884):
    put_word(ram, 0x42F5, box)
    ram[BASE + 0xA1F7:BASE + 0xA387] = bytes(reader.TEXT_WINDOW_BYTES)
    start = BASE + 0xA1F7
    ram[start:start + len(payload) + 1] = payload + b"\xff"


def test_reader_preserves_input_and_binds_rows_to_records():
    ram = authored_ram()
    before = bytes(ram)
    result = reader.describe(ram)
    assert bytes(ram) == before
    assert [row["label"]["ascii"] for row in result["menu"]["rows"]] == ["Authored alpha", "Authored beta"]
    assert [row["record_offset"] for row in result["menu"]["rows"]] == [0x21E8, 0x21F6]
    assert result["text_buffer_candidate"]["buffer_status"] == "zero_filled"
    assert "subject_name_candidate" not in result["conversation_witness"]


@pytest.mark.parametrize("ram", [b"", bytes(reader.RAM_BYTES - 1), bytes(reader.RAM_BYTES + 1), "not bytes"])
def test_snapshot_extent_and_type_are_explicit(ram):
    with pytest.raises(reader.SnapshotError, match="640 KiB"):
        reader.describe(ram)


@pytest.mark.parametrize("ds", [-1, 0, 0xFFFF, True])
def test_other_segment_bindings_are_not_silently_reused(ds):
    with pytest.raises(reader.SnapshotError, match="16F3"):
        reader.describe(authored_ram(), ds=ds)


@pytest.mark.parametrize("offset,value", [(0x2184, 0), (0x2184, 65), (0x2840, 0xFFFF),
                                          (0x2824, 0xFFFF), (0x4303, 0xFFFF), (0x4305, 0xA000)])
def test_counts_and_pointer_bounds_fail_closed(offset, value):
    ram = authored_ram()
    put_word(ram, offset, value)
    with pytest.raises(reader.SnapshotError):
        reader.describe(ram)


def test_menu_signed_skip_and_underflow():
    ram = authored_ram()
    ram[BASE + 0x2599] = 8
    ram[BASE + 0x25A2:BASE + 0x25AA] = ram[BASE + 0x259A:BASE + 0x25A2]
    result = reader.describe(ram)
    assert result["menu"]["page_skip"] == 8
    assert result["menu"]["rows"][0]["entry_offset"] == 0x25A2
    put_word(ram, 0x2824, 2)
    ram[BASE + 3] = 0x80
    with pytest.raises(reader.SnapshotError, match="wrap"):
        reader.describe(ram)


@pytest.mark.parametrize("field,value", [(0xFED8, 6), (0xFED5, 5)])
def test_menu_row_limits(field, value):
    ram = authored_ram()
    ram[BASE + field] = value
    with pytest.raises(reader.SnapshotError, match="five-row"):
        reader.describe(ram)


def test_active_geometry_and_row_callback_are_required():
    ram = authored_ram()
    put_word(ram, 0x21E8 + 4, 321)
    with pytest.raises(reader.SnapshotError, match="geometry"):
        reader.describe(ram)
    ram = authored_ram()
    put_word(ram, 0x21E8 + 12, 0x1234)
    with pytest.raises(reader.SnapshotError, match="callback"):
        reader.describe(ram)


@pytest.mark.parametrize("mode,handler", [(0, 0), (1, 0xCE6B), (0x80, 0xCE65), (0x81, 0xCE65)])
def test_paging_row_is_generated_instead_of_reading_a_normal_entry(mode, handler):
    ram = authored_ram()
    ram[BASE + 0xFED5] = 1
    ram[BASE + 0xFED4] = mode
    put_word(ram, 0x259E, 0)  # A normal entry would be invalid here.
    row = reader.describe(ram)["menu"]["rows"][1]
    assert row["source"] == "generated_paging_row"
    assert row["handler"] == handler
    assert row["label"]["ascii"] == "Authored next page"


def test_text_read_cannot_cross_segment_or_scan_past_its_budget():
    ram = authored_ram()
    struct.pack_into("<H", ram, TEXT_SEGMENT * 16 + TEXT_TABLE, 0xFFFE)
    start = TEXT_SEGMENT * 16 + 0xFFFE
    ram[start:start + 3] = b"AA\xff"  # Terminator exists, but in the next segment.
    with pytest.raises(reader.SnapshotError, match="terminator"):
        reader.describe(ram)
    ram = authored_ram()
    start = TEXT_SEGMENT * 16 + 0x0400
    ram[start:start + reader.MAX_LABEL_BYTES + 1] = b"A" * reader.MAX_LABEL_BYTES + b"\xff"
    with pytest.raises(reader.SnapshotError, match="terminator"):
        reader.describe(ram)


def test_labels_escape_controls_and_keep_phrase_expansion_unqualified():
    ram = authored_ram()
    put_label(ram, 1, b"Alpha\rBeta\x01\x80")
    label = reader.describe(ram)["menu"]["rows"][0]["label"]
    assert label["ascii"] == "Alpha\nBeta\\x01\\x80"
    assert label["ascii_only"] is False
    assert label["unexpanded_control_bytes"] == [1, 0x80]
    put_word(ram, 0x259A, 0x0801)
    put_label(ram, 0x0801, b"Authored phrase\xe0", phrase=True)
    label = reader.describe(ram)["menu"]["rows"][0]["label"]
    assert label["table_slot"] == 0x4307
    assert label["lookup_kind"] == "phrase_candidate"
    assert label["ascii"].endswith("\\xe0")


def test_compact_line_remains_candidate_and_disappears_after_box_closes():
    ram = authored_ram(conversation=True)
    put_speech(ram, b"An entirely authored line.")
    result = reader.describe(ram)
    view = reader.compact(result)
    assert view["subject_name_candidate"] == "Authored speaker"
    assert view["dialogue"]["line_candidate"] == "An entirely authored line."
    assert view["dialogue"]["rendered_currentness"] == "unqualified"
    put_word(ram, 0x42F5, 0)
    closed = reader.describe(ram)
    assert closed["text_buffer_candidate"]["ascii_projection"] == "An entirely authored line."
    assert reader.compact(closed)["dialogue"]["line_candidate"] is None
    assert reader.compact(closed)["dialogue"]["status"] == "conversation_box_inactive"
    assert reader.compact(closed)["dialogue"]["other_presentations"] == "map/status presentation unqualified"


def test_compact_withholds_controlled_or_unterminated_text():
    ram = authored_ram()
    put_speech(ram, b"Unexpanded\x81text")
    result = reader.describe(ram)
    assert result["text_buffer_candidate"]["ascii_projection"] == "Unexpanded\\x81text"
    assert reader.compact(result)["dialogue"]["status"] == "unexpanded_controls"
    ram[BASE + 0xA1F7:BASE + 0xA387] = b"A" * reader.TEXT_WINDOW_BYTES
    assert reader.compact(reader.describe(ram))["dialogue"]["status"] == "incomplete_or_empty_buffer"


def test_admission_excludes_highlight_but_retains_guard_and_route_changes():
    ram = authored_ram()
    baseline = reader.describe(ram)["menu_admission_sha256"]
    put_word(ram, 0x259A, 0x8001)
    assert reader.describe(ram)["menu_admission_sha256"] == baseline
    put_word(ram, 0x259A, 0x4001)
    assert reader.describe(ram)["menu_admission_sha256"] != baseline
    ram = authored_ram()
    put_word(ram, 0x2186 + 12, 0x5678)  # A non-row target also invalidates the digest.
    assert reader.describe(ram)["menu_admission_sha256"] != baseline


def test_dialogue_context_invalidates_admission_but_text_has_separate_witness():
    ram = authored_ram(conversation=True)
    put_speech(ram, b"Authored first line")
    before = reader.describe(ram)
    put_speech(ram, b"Authored next line")
    changed_text = reader.describe(ram)
    assert changed_text["menu_admission_sha256"] == before["menu_admission_sha256"]
    assert changed_text["dialogue_witness_sha256"] != before["dialogue_witness_sha256"]
    put_word(ram, 0x4315, 1)
    assert reader.describe(ram)["menu_admission_sha256"] != changed_text["menu_admission_sha256"]
    stable = reader.describe(ram)["dialogue_witness_sha256"]
    ram[BASE + 0xA386] = 7  # Stale tail after the first terminator is irrelevant.
    put_word(ram, 0x42F5, 0x288C)  # Layout alone is not dialogue progress.
    assert reader.describe(ram)["dialogue_witness_sha256"] == stable


def test_opaque_dialogue_fields_do_not_claim_story_semantics():
    ram = authored_ram(conversation=True)
    for offset, value in ((0x4311, 0x1234), (0x4315, 3), (0x42F9, 0x4567),
                          (0x000E, 0x0055), (0x0014, 0x00AA)):
        put_word(ram, offset, value)
    ram[BASE + 0x4319] = 0x80
    witness = reader.describe(ram)["conversation_witness"]
    assert {key: witness[key] for key in ("dialogue_record_4311", "dialogue_selector_4315",
                                        "dialogue_mask_4319", "subject_record_42f9",
                                        "entry_bitset_000e", "entry_bitset_0014")} == {
        "dialogue_record_4311": 0x1234, "dialogue_selector_4315": 3,
        "dialogue_mask_4319": 0x80, "subject_record_42f9": 0x4567,
        "entry_bitset_000e": 0x0055, "entry_bitset_0014": 0x00AA}
    assert "story_complete" not in witness and "input_ready" not in witness


def authored_map():
    ram = authored_ram()
    ram[BASE + 0x4247] = 1
    put_word(ram, 0x0006, 0x0180)
    put_word(ram, 0x114E, 0x0100)
    put_word(ram, 0x4258, 0x011C)
    for pointer, first_id, second_part in ((0x0100, 1, 2), (0x011C, 2, 3)):
        ram[BASE + pointer] = first_id
        ram[BASE + pointer + 1] = second_part
    put_label(ram, 14, b"Authored suffix", offset=0x0500)
    put_label(ram, 15, b"Other suffix", offset=0x0540)
    struct.pack_into("<3H", ram, BASE + 0xA107, 0x0100, 100, 0x0100 | 70)
    struct.pack_into("<3H", ram, BASE + 0xA10D, 0x011C, 120, 0x0100 | 80)
    return ram


def test_map_points_bind_screen_context_and_site_names_without_claiming_arrival():
    ram = authored_map()
    site = reader.describe(ram)["site_witness"]
    assert site["site_location_context"] is True
    assert site["current_record_114e"] == 0x0100
    assert site["selected_record_4258"] == 0x011C
    assert [point["screen_xy"] for point in site["rendered_map_points"]] == [[100, 70], [120, 80]]
    assert [point["site"]["name_candidate"] for point in site["rendered_map_points"]] == [
        "Authored alpha Authored suffix", "Authored beta-Other suffix"]
    assert "arrival" not in site
    ram[BASE + 0x4247] = 0
    assert reader.describe(ram)["site_witness"]["rendered_map_points"] == []


def test_map_points_exclude_other_modes_and_do_not_dereference_direction_selectors():
    ram = authored_map()
    put_word(ram, 0xA10D + 4, 0x0200 | 80)
    put_word(ram, 0x4258, 0xFFF1)
    site = reader.describe(ram)["site_witness"]
    assert len(site["rendered_map_points"]) == 1
    assert site["selected_name_candidate"]["name_candidate"] is None
    assert site["selected_name_candidate"]["qualification"] == "unrecognized_or_direction_pointer"


def test_site_selection_and_map_mode_invalidate_admission():
    ram = authored_map()
    baseline = reader.describe(ram)["menu_admission_sha256"]
    put_word(ram, 0x4258, 0x0100)
    assert reader.describe(ram)["menu_admission_sha256"] != baseline
    ram = authored_map()
    put_word(ram, 0x114E, 0x011C)
    assert reader.describe(ram)["menu_admission_sha256"] != baseline
    ram = authored_map()
    ram[BASE + 0x4247] = 0
    assert reader.describe(ram)["menu_admission_sha256"] != baseline


def test_map_point_list_is_bounded_before_text_buffer():
    ram = authored_map()
    for index in range(reader.MAX_MAP_POINTS):
        struct.pack_into("<3H", ram, BASE + 0xA107 + 6 * index, 0x0100, 100, 0x0100 | 70)
    with pytest.raises(reader.SnapshotError, match="terminator before the text buffer"):
        reader.describe(ram)


@pytest.mark.parametrize("pointer,x,y", [(0x0101, 100, 70), (0x0100, 320, 70), (0x0100, 100, 200)])
def test_invalid_map_point_geometry_or_site_binding_is_refused(pointer, x, y):
    ram = authored_map()
    struct.pack_into("<3H", ram, BASE + 0xA107, pointer, x, 0x0100 | y)
    with pytest.raises(reader.SnapshotError):
        reader.describe(ram)


def sparse_capture(ram):
    calls = []

    def read(address, length):
        assert 0 <= address <= len(ram) - length and length > 0
        calls.append((address, length))
        return ram[address:address + length]

    return reader.describe_sparse(read), calls


@pytest.mark.parametrize("kind", ["ordinary", "conversation", "stale", "controls", "phrase", "paging", "map"])
def test_sparse_observation_preserves_the_complete_full_reader_contract(kind):
    ram = authored_map() if kind == "map" else authored_ram(conversation=kind in ("conversation", "stale"))
    if kind in ("conversation", "stale"):
        put_speech(ram, b"Authored speech", box=0 if kind == "stale" else 0x2884)
    elif kind == "controls":
        put_label(ram, 1, b"Alpha\rBeta\x01\x80")
    elif kind == "phrase":
        put_word(ram, 0x259A, 0x0801)
        put_label(ram, 0x0801, b"Authored phrase\xe0", phrase=True)
    elif kind == "paging":
        ram[BASE + 0xFED5] = 1
        ram[BASE + 0xFED4] = 0x80
        put_word(ram, 0x259E, 0)
    before = bytes(ram)
    result, calls = sparse_capture(ram)
    expected = reader.describe(ram)
    assert result["observation"] == expected
    assert reader.compact(result["observation"]) == reader.compact(expected)
    assert bytes(ram) == before
    receipts = result["reads"]
    assert receipts["calls"] == len(calls) <= 5
    assert receipts["bytes"] == sum(length for _, length in calls) < reader.RAM_BYTES // 20
    assert [(entry["address"], entry["length"]) for entry in receipts["ranges"]] == calls
    for entry in receipts["ranges"]:
        start, length = entry["address"], entry["length"]
        assert entry["sha256"] == hashlib.sha256(ram[start:start + length]).hexdigest()
    ordered = sorted(calls)
    assert all(start + length <= next_start for (start, length), (next_start, _) in zip(ordered, ordered[1:]))


def test_sparse_capture_retains_real_ranges_and_can_be_replayed_without_zero_filling():
    result, _ = sparse_capture(authored_map())
    capture = result["capture"]
    blocks = [(item["address"], bytes.fromhex(item["data_hex"])) for item in capture["ranges"]]

    def read(address, length):
        for start, block in blocks:
            if start <= address and address + length <= start + len(block):
                return block[address - start:address - start + length]
        raise LookupError("No retained bytes at the requested address")

    assert reader.describe_sparse(read) == result
    assert all(any(start <= dep["address"] and dep["address"] + dep["length"] <= start + len(block)
                   for start, block in blocks) for dep in capture["dependencies"])
    with pytest.raises(LookupError, match="No retained bytes"):
        read(0, 1)


def test_dependency_digest_excludes_prefetched_gaps_but_binds_raw_witness_changes():
    ram = authored_ram()
    baseline, _ = sparse_capture(ram)
    # This byte was fetched in the coalesced core range but never parsed.
    ram[BASE + 0x4000] ^= 0x42
    unrelated, _ = sparse_capture(ram)
    assert unrelated["observation"] == baseline["observation"]
    assert unrelated["capture"]["sha256"] != baseline["capture"]["sha256"]
    assert unrelated["capture"]["dependency_sha256"] == baseline["capture"]["dependency_sha256"]
    # Hover is deliberately absent from menu admission, but remains captured.
    put_word(ram, 0x259A, 0x8001)
    changed, _ = sparse_capture(ram)
    assert changed["observation"]["menu_admission_sha256"] == baseline["observation"]["menu_admission_sha256"]
    assert changed["capture"]["dependency_sha256"] != baseline["capture"]["dependency_sha256"]


@pytest.mark.parametrize("failing_call", range(4))
@pytest.mark.parametrize("bad_reply", ["short", "oversized", "not_bytes"])
def test_sparse_missing_bytes_are_never_replaced_by_zeros(failing_call, bad_reply):
    ram, calls = authored_ram(), []

    def read(address, length):
        index = len(calls)
        calls.append((address, length))
        if index == failing_call:
            return {"short": bytes(length - 1), "oversized": bytes(length + 1), "not_bytes": None}[bad_reply]
        return ram[address:address + length]

    with pytest.raises(reader.SnapshotError, match="must return exactly"):
        reader.describe_sparse(read)
    assert len(calls) == failing_call + 1


def test_sparse_callback_exception_stops_the_capture_and_is_not_hidden():
    calls, failure = [], OSError("Authored read failure")

    def read(address, length):
        calls.append((address, length))
        raise failure

    with pytest.raises(OSError) as error:
        reader.describe_sparse(read)
    assert error.value is failure and len(calls) == 1


@pytest.mark.parametrize("offset,value", [(0x2184, 0), (0x2184, 65), (0x2840, 0xFFFF),
                                          (0x2824, 0xFFFF), (0x4303, 0xFFFF), (0x4305, 0xA000)])
def test_sparse_pointer_failures_match_full_reader_without_out_of_range_callback(offset, value):
    ram = authored_ram()
    put_word(ram, offset, value)
    with pytest.raises(reader.SnapshotError):
        reader.describe(ram)
    with pytest.raises(reader.SnapshotError):
        sparse_capture(ram)


@pytest.mark.parametrize("offset", [0x5000, 0xFFFE])
def test_sparse_menu_outside_prefetched_core_is_read_from_its_actual_pointer(offset):
    ram = authored_ram()
    old_entries = bytes(ram[BASE + 0x259A:BASE + 0x25A2])
    put_word(ram, 0x2824, offset)
    skip = -16 if offset == 0xFFFE else 0
    ram[BASE + offset:BASE + offset + 2] = bytes((0xFF, skip & 0xFF))
    first = offset + 2 + skip
    ram[BASE + first:BASE + first + 8] = old_entries
    result, calls = sparse_capture(ram)
    assert result["observation"] == reader.describe(ram)
    assert result["structure_witness"]["menu"] == offset
    assert any(address <= BASE + offset < address + length for address, length in calls)


def test_sparse_pointer_rebinding_after_restore_has_no_cross_observation_cache():
    ram = authored_ram()
    initial, _ = sparse_capture(ram)
    new_segment, new_table = 0x5000, 0x0020
    put_word(ram, 0x4303, new_table)
    put_word(ram, 0x4305, new_segment)
    for index, payload in enumerate((b"Restored alpha", b"Restored beta")):
        pointer = 0x0800 + 0x80 * index
        struct.pack_into("<H", ram, new_segment * 16 + new_table + 2 * index, pointer)
        ram[new_segment * 16 + pointer:new_segment * 16 + pointer + len(payload) + 1] = payload + b"\xff"
    restored, calls = sparse_capture(ram)
    assert restored["observation"] == reader.describe(ram)
    assert restored["observation"]["menu"]["rows"][0]["label"]["ascii"] == "Restored alpha"
    assert restored["capture"]["dependency_sha256"] != initial["capture"]["dependency_sha256"]
    assert any(new_segment * 16 <= address < new_segment * 16 + 65536 for address, _ in calls)
    assert not any(TEXT_SEGMENT * 16 <= address < TEXT_SEGMENT * 16 + 65536 for address, _ in calls)


def test_sparse_bounded_label_window_is_not_extended_to_find_a_late_terminator():
    ram = authored_ram()
    start = TEXT_SEGMENT * 16 + 0x0400
    ram[start:start + reader.MAX_LABEL_BYTES + 1] = b"A" * reader.MAX_LABEL_BYTES + b"\xff"
    for parse in (reader.describe, lambda value: sparse_capture(value)[0]):
        with pytest.raises(reader.SnapshotError, match="terminator"):
            parse(ram)


@pytest.mark.parametrize("limit,value", [("SPARSE_MAX_BYTES", 1), ("SPARSE_MAX_READS", 3)])
def test_sparse_read_budget_is_checked_before_admitting_more_reads(monkeypatch, limit, value):
    monkeypatch.setattr(reader, limit, value)
    ram, calls = authored_ram(), []

    def read(address, length):
        calls.append((address, length))
        return ram[address:address + length]

    with pytest.raises(reader.SnapshotError, match="budget"):
        reader.describe_sparse(read)
    assert len(calls) == (0 if limit == "SPARSE_MAX_BYTES" else 3)


@pytest.mark.parametrize("kind", ["ordinary", "conversation", "paging", "map"])
def test_sparse_structure_matches_independent_legacy_full_segment_witness(kind):
    spec = importlib.util.spec_from_file_location(
        "dune_progress_for_reader_test", Path(__file__).resolve().parents[1] / "scripts/experiments/dune_progress.py")
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    ram = authored_map() if kind == "map" else authored_ram(conversation=kind == "conversation")
    if kind == "paging":
        ram[BASE + 0xFED5] = 1
        ram[BASE + 0xFED4] = 0x80
        put_word(ram, 0x259E, 0x1234)
        put_word(ram, 0x25A0, 0x5678)
    expected = controller._structure(ram[BASE:BASE + 65536])
    full, _ = sparse_capture(ram)
    result = reader.read_structure_sparse(lambda address, length: ram[address:address + length])
    assert result["structure_witness"] == expected == full["structure_witness"]
    assert result["reads"]["calls"] == 2
    assert result["reads"]["bytes"] == 17182
    if kind == "paging":
        assert result["structure_witness"]["entries"][1] == [0x1234, 0x5678]
        assert full["observation"]["menu"]["rows"][1]["handler"] == 0xCE65


def compact_sha(packet):
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_changed_compact_initial_packet_is_complete_and_bound_to_full_contents():
    observation = reader.describe(authored_map())
    result = reader.changed_compact(None, observation)
    assert result["schema"] == "dune-compact-delta-1"
    assert result["kind"] == "full" and result["base_sha256"] is None
    assert result["fields"] == reader.compact(observation)
    assert result["current_sha256"] == compact_sha(result["fields"])
    # A returned packet keeps its identity even if a caller reuses its input.
    observation["location_key"]["word_0004"] ^= 1
    observation["site_witness"]["rendered_map_points"].clear()
    assert result["current_sha256"] == compact_sha(result["fields"])
    assert "scene_token" not in result and "input_ready" not in result


def test_changed_compact_replaces_whole_fields_and_reconstructs_the_current_packet():
    ram = authored_map()
    before = reader.describe(ram)
    put_word(ram, 4, 0x1234)
    put_word(ram, 0x4258, 0x0100)
    put_label(ram, 1, b"Changed authored choice")
    after = reader.describe(ram)
    delta = reader.changed_compact(before, after)
    initial, current = reader.compact(before), reader.compact(after)
    assert delta["kind"] == "delta"
    assert delta["base_sha256"] == compact_sha(initial)
    assert delta["current_sha256"] == compact_sha(current)
    assert {**initial, **delta["fields"]} == current
    assert delta["fields"]["choices"] == current["choices"]
    assert delta["fields"]["sites"] == current["sites"]
    assert "subject_selector" not in delta["fields"]
    assert "controls" not in delta["fields"] and "text_buffer_candidate" not in delta["fields"]


def test_changed_compact_base_hash_covers_unchanged_fields_and_rejects_a_wrong_cache():
    ram = authored_ram(conversation=True)
    put_speech(ram, b"Authored first line")
    before = reader.describe(ram)
    put_speech(ram, b"Authored next line")
    after = reader.describe(ram)
    delta = reader.changed_compact(before, after)
    assert "choices" not in delta["fields"]
    wrong_cache = reader.compact(before)
    wrong_cache["choices"][0]["label"] = "Wrong retained choice"
    assert compact_sha(wrong_cache) != delta["base_sha256"]
    assert compact_sha({**wrong_cache, **delta["fields"]}) != delta["current_sha256"]


@pytest.mark.parametrize("kind", ["inactive", "controls", "unterminated"])
def test_changed_compact_withholds_stale_or_unexpanded_dialogue_exactly_like_compact(kind):
    ram = authored_ram(conversation=True)
    put_speech(ram, b"Authored visible candidate")
    before = reader.describe(ram)
    if kind == "inactive":
        put_word(ram, 0x42F5, 0)
    elif kind == "controls":
        put_speech(ram, b"Authored control\x02")
    else:
        ram[BASE + 0xA1F7:BASE + 0xA387] = b"A" * reader.TEXT_WINDOW_BYTES
    after = reader.describe(ram)
    delta = reader.changed_compact(before, after)
    assert delta["fields"]["dialogue"] == reader.compact(after)["dialogue"]
    assert delta["fields"]["dialogue"]["line_candidate"] is None
    assert delta["fields"]["dialogue"]["rendered_currentness"] == "unqualified"
    assert "ascii_projection" not in json.dumps(delta)


def test_changed_compact_equal_views_produce_empty_fields_without_an_input_token():
    ram = authored_ram(conversation=True)
    put_speech(ram, b"Authored line")
    before = reader.describe(ram)
    # Unused trailing text bytes alter raw evidence but do not change compact.
    ram[BASE + 0xA386] = 0xAA
    after = reader.describe(ram)
    assert before["text_buffer_candidate"]["window_sha256"] != after["text_buffer_candidate"]["window_sha256"]
    delta = reader.changed_compact(before, after)
    assert delta["kind"] == "delta" and delta["fields"] == {}
    assert delta["base_sha256"] == delta["current_sha256"] == compact_sha(reader.compact(after))
    assert "scene_token" not in delta and "input_ready" not in delta
