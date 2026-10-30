"""Independent, authored Z-machine v3 processor acceptance examples.

The byte encodings and expected destinations below come from the public
Z-machine specification, not the converter or the processor implementation.
The tiny checksummed stories contain no original Zork data.

Specification: https://inform-fiction.org/zmachine/standards/z1point1/
Sections 4 (encoding), 5 (routine headers), 6 (calls and saved state), and
15 (jump, save, restore, restart, return and opcode operand counts).
"""

import hashlib

import pytest

from fdisbull.processor import Location, decode_instruction
from fdisbull.zmachine_processor import ZMachineV3Processor


ENTRY = 900


def story_with(code, *, at=ENTRY, patches=(), padding=b""):
    """Build an authored v3 source snapshot with independently placed code."""
    data = bytearray(1024)

    def word(offset, value):
        data[offset:offset + 2] = value.to_bytes(2, "big")

    data[0] = 3
    # Tables occupy separate ranges; the initial PC names an instruction,
    # not a routine header. Header and checksum qualification are deliberate.
    for offset, value in ((2, 1), (4, 900), (6, ENTRY), (8, 810),
                          (10, 544), (12, 64), (14, 800), (24, 606),
                          (26, 512)):
        word(offset, value)
    data[18:24] = b"261029"
    data[810:814] = bytes([0, 4, 0, 0])
    data[ENTRY] = 0xBA  # A valid terminal entry when the example is elsewhere.
    data[at:at + len(code)] = code
    for offset, payload in patches:
        data[offset:offset + len(payload)] = payload
    word(28, sum(data[64:]) & 0xFFFF)
    return bytes(data) + padding


def instruction(code, *, at=ENTRY, patches=()):
    processor = ZMachineV3Processor(story_with(code, at=at, patches=patches))
    result = decode_instruction(
        processor, processor.program, Location(processor.info.address_space, at)
    )
    assert result is not None
    return processor, result


def edges(result):
    return [(edge.kind, None if edge.target is None else edge.target.offset)
            for edge in result.successors]


def test_branch_on_false_retains_polarity_and_independent_destinations():
    processor, result = instruction(bytes.fromhex("90 00 44"))
    assert result.facts["op"] == result.facts["mnemonic"] == "jz"
    assert result.facts["size"] == 3
    assert result.facts["branch"]["when"] is False
    assert result.facts["branch"]["offset"] == 4
    assert edges(result) == [("branch", 905), ("fallthrough", 903)]
    assert all(edge.target.space == processor.info.address_space
               for edge in result.successors if edge.target is not None)


def test_signed_long_branch_is_relative_to_end_of_branch_data():
    _, result = instruction(bytes.fromhex("90 01 bf fe"))
    assert result.facts["branch"]["offset"] == -2
    assert edges(result) == [("branch", 900), ("fallthrough", 904)]


@pytest.mark.parametrize(("encoded", "returned"), [("90 01 c0", False),
                                                   ("90 01 c1", True)])
def test_branch_offsets_zero_and_one_return_instead_of_addressing_memory(encoded, returned):
    _, result = instruction(bytes.fromhex(encoded))
    assert result.facts["branch"]["return"] is returned
    assert result.facts["branch"]["target"] is None
    assert edges(result) == [("return", None), ("fallthrough", 903)]


@pytest.mark.parametrize(("encoded", "destination"), [("8c ff fd", 898),
                                                      ("9c 05", 905)])
def test_unconditional_jump_uses_signed_word_value_without_a_fallthrough(encoded, destination):
    _, result = instruction(bytes.fromhex(encoded))
    assert result.facts["flow"] == "jump"
    assert edges(result) == [("branch", destination)]


def test_variable_jump_stays_unknown_even_when_initial_global_value_is_zero():
    _, result = instruction(bytes.fromhex("ac 10"))
    assert result.facts["operands"] == [{"kind": "variable", "value": 16}]
    assert result.facts["flow"] == "indirect_jump"
    assert edges(result) == [("branch", None)]


@pytest.mark.parametrize(("at", "code", "raw_target"), [
    (64, "8c ff fd", 62),
    (900, "8c 01 00", 1157),
])
def test_invalid_static_jump_target_is_retained_as_unresolved(at, code, raw_target):
    _, result = instruction(bytes.fromhex(code), at=at)
    assert edges(result) == [("branch", None)]
    # The invalid value remains observable rather than wrapped into a valid PC.
    assert str(raw_target) in result.successors[0].evidence or hex(raw_target) in result.successors[0].evidence


def test_call_unpacks_routine_and_skips_initial_local_values():
    _, result = instruction(bytes.fromhex("e0 3f 01 e0 10"),
                            patches=((960, bytes.fromhex("02 12 34 ab cd b0")),))
    assert result.facts["op"] == "call"
    assert result.facts["size"] == 5
    assert result.facts["store"] == 16
    assert result.facts["call"]["packed_address"] == 480
    assert result.facts["call"]["routine_header"] == 960
    assert result.facts["call"]["entry"] == 965
    assert result.facts["call"]["local_count"] == 2
    assert result.facts["call"]["initial_locals"] == [0x1234, 0xABCD]
    assert edges(result) == [("call", 965), ("fallthrough", 905)]


def test_null_call_does_not_decode_header_zero_or_add_a_call_edge():
    _, result = instruction(bytes.fromhex("e0 7f 00 10"))
    assert result.facts["operands"] == [{"kind": "small", "value": 0}]
    assert result.facts["store"] == 16
    assert result.facts["call"]["packed_address"] == 0
    assert edges(result) == [("fallthrough", 904)]


def test_variable_call_does_not_treat_variable_number_as_a_packed_address():
    _, result = instruction(bytes.fromhex("e0 bf 10 11"))
    assert result.facts["operands"] == [{"kind": "variable", "value": 16}]
    assert result.facts["store"] == 17
    assert result.facts["flow"] == "indirect_call"
    assert result.facts["call"]["routine_header"] is None
    assert edges(result) == [("call", None), ("fallthrough", 904)]


@pytest.mark.parametrize(("packed", "patches"), [
    (480, ((960, bytes.fromhex("10 b0")),)),  # More than 15 locals.
    (511, ((1022, bytes.fromhex("01 00")),)),  # Missing initial local/entry.
    (512, ()),  # Header at declared EOF.
])
def test_invalid_call_header_does_not_become_a_guessed_entry(packed, patches):
    code = b"\xe0\x3f" + packed.to_bytes(2, "big") + b"\x10"
    _, result = instruction(code, patches=patches)
    # Invalid calculated offsets remain in evidence, not in the qualified
    # candidate entry field or the traversable successor.
    assert result.facts["call"]["entry"] is None
    assert result.facts["call"]["status"] == "invalid_routine_header"
    assert edges(result) == [("call", None), ("fallthrough", 905)]


def test_callable_routine_in_dynamic_memory_is_not_rejected_by_high_memory_mark():
    _, result = instruction(bytes.fromhex("e0 3f 01 5e 10"),
                            patches=((700, bytes.fromhex("00 b0")),))
    assert result.facts["call"]["routine_header"] == 700
    assert result.facts["call"]["entry"] == 701
    assert edges(result) == [("call", 701), ("fallthrough", 905)]


def test_initial_pc_is_an_instruction_address_without_a_routine_header():
    processor = ZMachineV3Processor(story_with(bytes.fromhex("ba")))
    assert processor.story_info["initial_pc"] == ENTRY
    result = decode_instruction(processor, processor.program,
                                Location(processor.info.address_space, ENTRY))
    assert result.facts["op"] == "quit"
    assert not any(edge.kind == "fallthrough" for edge in result.successors)


@pytest.mark.parametrize(("opcode", "expected_edges"), [
    (0xB2, [("fallthrough", 903)]),
    (0xB3, [("return", None)]),
])
def test_inline_text_belongs_to_the_instruction_span(opcode, expected_edges):
    _, result = instruction(bytes([opcode, 0x98, 0xE8]))
    assert result.facts["text_offset"] == 901
    assert result.facts["size"] == 3
    assert result.facts["end"] == 903
    assert edges(result) == expected_edges


@pytest.mark.parametrize("code", ["b0", "b1", "b8", "9b 01", "ab 00"])
def test_return_opcodes_have_no_local_fallthrough(code):
    _, result = instruction(bytes.fromhex(code))
    assert result.facts["flow"] == "return"
    assert edges(result) == [("return", None)]


@pytest.mark.parametrize(("code", "expected_edges"), [
    ("b5 c4", [("branch", 904), ("fallthrough", 902)]),
    ("b5 44", [("branch", 904), ("fallthrough", 902)]),
])
def test_save_retains_both_outcomes_and_raw_branch_polarity(code, expected_edges):
    _, result = instruction(bytes.fromhex(code))
    assert result.facts["branch"]["when"] is (code == "b5 c4")
    assert edges(result) == expected_edges


@pytest.mark.parametrize(("code", "failure_edge"), [
    ("b6 c4", ("fallthrough", 902)),
    ("b6 44", ("branch", 904)),
    ("b6 41", ("return", None)),
])
def test_restore_success_is_saved_continuation_and_only_failure_follows_local_branch(code, failure_edge):
    _, result = instruction(bytes.fromhex(code))
    assert result.facts["flow"] == "restore"
    assert edges(result) == [("restore", None), failure_edge]


def test_restart_targets_original_initial_pc_without_a_local_fallthrough():
    _, result = instruction(bytes.fromhex("b7"), at=950)
    assert result.facts["flow"] == "restart"
    assert edges(result) == [("restart", ENTRY)]


def test_four_operand_je_is_supported_in_variable_form():
    _, result = instruction(bytes.fromhex("c1 55 01 02 03 04 c1"))
    assert result.facts["op"] == "je"
    assert result.facts["operands"] == [
        {"kind": "small", "value": value} for value in (1, 2, 3, 4)
    ]
    assert result.facts["size"] == 7
    assert edges(result) == [("return", None), ("fallthrough", 907)]


@pytest.mark.parametrize("code", [
    "d4 7f 01 10",  # Variable-form add with only one operand.
    "c1 7f 01 c1",  # je also requires at least two operands.
    "e0 ff 10",  # No routine operand in call.
    "e1 5f 01 02",  # storew needs three operands.
    "e4 55 01 02 03 04",  # Timed sread is not a v3 instruction form.
    "e0 cf",  # An omitted type may not be followed by another operand.
    "ec ff",  # call_vs2 belongs to a later story version.
    "be",  # Extended opcodes are not available in v3.
])
def test_malformed_or_wrong_version_instruction_fails_explicitly(code):
    processor = ZMachineV3Processor(story_with(bytes.fromhex(code)))
    with pytest.raises(ValueError):
        decode_instruction(processor, processor.program,
                           Location(processor.info.address_space, ENTRY))


@pytest.mark.parametrize("code", ["14 02 03", "90 00 80", "b2 00", "e0 3f 01"])
def test_truncation_uses_declared_image_end_even_when_file_has_padding(code):
    encoded = bytes.fromhex(code)
    start = 1024 - len(encoded)
    processor = ZMachineV3Processor(story_with(encoded, at=start, padding=b"\0" * 64))
    with pytest.raises(ValueError, match="[Tt]runcat"):
        decode_instruction(processor, processor.program,
                           Location(processor.info.address_space, start))


def test_identity_binds_full_file_but_padding_is_not_executable():
    first_raw = story_with(b"\xba", padding=b"first")
    second_raw = story_with(b"\xba", padding=b"other")
    first = ZMachineV3Processor(first_raw)
    second = ZMachineV3Processor(second_raw)
    assert isinstance(first.program, bytes)
    assert first.program == first_raw
    assert first.info.address_unit == "byte"
    assert hashlib.sha256(first_raw).hexdigest() in first.info.address_space
    assert first.info.address_space != second.info.address_space
    assert first.story_info["declared_bytes"] == 1024
    assert first.story_info["trailing_bytes"] == 5
    assert decode_instruction(first, first.program,
                              Location(first.info.address_space, 1024)) is None
    with pytest.raises(ValueError):
        decode_instruction(first, second.program, Location(first.info.address_space, ENTRY))
    with pytest.raises(ValueError, match="address space"):
        decode_instruction(first, first.program, Location(second.info.address_space, ENTRY))


def test_decoded_facts_do_not_mutate_the_original_program():
    processor, result = instruction(bytes.fromhex("14 02 03 10"))
    original = processor.program
    original_digest = hashlib.sha256(original).hexdigest()
    result.facts["operands"][0]["value"] = 999
    result.facts["bytes"] = "00"
    again = decode_instruction(processor, processor.program,
                               Location(processor.info.address_space, ENTRY))
    assert again.facts["operands"][0] == {"kind": "small", "value": 2}
    assert again.facts["bytes"] == "14020310"
    assert processor.program == original
    assert hashlib.sha256(processor.program).hexdigest() == original_digest


def test_recursive_analysis_reports_routine_header_inside_a_call_instruction(tmp_path):
    from fdisbull.zmachine_analysis import analyze_story

    # The call names packed451 -> header902, inside its own operand bytes.
    # Those bytes happen to describe one local and entry905. Decodability does
    # not resolve the incompatible code/header interpretations.
    path = tmp_path / "overlapping-header.z3"
    path.write_bytes(story_with(bytes.fromhex("e0 3f 01 c3 10 ba")))
    result = analyze_story(path)
    assert not result["complete"]
    assert result["worklist_drained"]
    assert any(issue["kind"] == "routine_header_overlaps_instruction"
               and issue["routine_header"] == 902
               and 900 in issue["instruction_starts"]
               for issue in result["issues"])


def test_recursive_analysis_reports_branch_into_previously_found_routine_header(tmp_path):
    from fdisbull.zmachine_analysis import analyze_story

    # The first call qualifies header960..964 and entry965. Its continuation
    # then jumps to961, which can decode but is within those default locals.
    path = tmp_path / "branch-into-header.z3"
    path.write_bytes(story_with(bytes.fromhex("e0 3f 01 e0 10 8c 00 37"),
                                patches=((960, bytes.fromhex("02 12 34 ab cd b0")),)))
    result = analyze_story(path)
    assert not result["complete"]
    assert any(issue["kind"] == "instruction_overlaps_routine_header"
               and issue["offset"] == 961
               and 960 in issue["routine_headers"]
               for issue in result["issues"])


def test_byte_budget_preserves_unadmitted_candidate_in_recursive_frontier(tmp_path, monkeypatch):
    from fdisbull import zmachine_analysis

    path = tmp_path / "byte-budget.z3"
    path.write_bytes(story_with(bytes.fromhex("b4 b4 ba")))
    monkeypatch.setattr(zmachine_analysis, "MAX_DECODED_BYTES", 2)
    result = zmachine_analysis.analyze_story(path, max_instructions=10)
    assert result["status"] == "byte_budget"
    assert result["instruction_count"] == 2
    assert result["decoded_bytes"] == result["max_decoded_bytes"] == 2
    assert [item["offset"] for item in result["frontier"]] == [902]
    assert not result["worklist_drained"] and not result["complete"]


def test_exact_instruction_limit_is_not_a_budget_stop_when_loop_already_closed(tmp_path):
    from fdisbull.zmachine_analysis import analyze_story

    path = tmp_path / "self-loop.z3"
    path.write_bytes(story_with(bytes.fromhex("8c ff ff")))
    result = analyze_story(path, max_instructions=1)
    assert result["instruction_count"] == result["decode_attempts"] == 1
    assert not result["frontier"]
    assert result["status"] == "static_worklist_drained"
    assert result["complete"] and result["worklist_drained"]
    assert not result["runtime_reachability_proven"]
