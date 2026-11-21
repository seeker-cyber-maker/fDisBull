"""Authored AGI bytes only; no commercial game, save or native runtime."""

from hashlib import sha256
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

import pytest

from dotbox.agi_layout import logic_layout
from dotbox.agi_resources import V2Resources, logic_messages
from dotbox.agi_scenes import inspect_scenes


def _payload(code, messages=()):
    """Author a V2 LOGIC, with offsets relative to its message table."""
    strings = bytearray()
    offsets = bytearray()
    first_string = 2 + 2 * len(messages)
    for message in messages:
        offsets.extend((first_string + len(strings)).to_bytes(2, "little"))
        strings.extend(message.encode("ascii") + b"\0")
    encrypted = bytes(value ^ b"Avis Durgan"[i % 11] for i, value in enumerate(strings))
    section = (bytes([len(messages)]) + (first_string + len(strings)).to_bytes(2, "little")
               + offsets + encrypted)
    return len(code).to_bytes(2, "little") + code + section


def _bundle(root, logics=None):
    """Author split V2 directories and one volume; no installed game inputs."""
    root.mkdir(mode=0o700)
    if logics is None:
        # v30=7; v31=v30; set f42; if f42: reset f42; new.room.v(v31); return.
        code = bytes.fromhex("031e07 041f1e 0c2a ff072aff0400 0d2a 131f 00")
        logics = {0: _payload(code, ["Authored fixture message"]), 7: _payload(b"\0")}
    directory = bytearray(b"\xff\xff\xff" * (max(logics) + 1))
    volume = bytearray()
    for number, payload in sorted(logics.items()):
        directory[3 * number:3 * number + 3] = len(volume).to_bytes(3, "big")
        volume.extend(b"\x12\x34\0" + len(payload).to_bytes(2, "little") + payload)
    (root / "LOGDIR").write_bytes(directory)
    for name in ("PICDIR", "VIEWDIR", "SNDDIR"):
        (root / name).write_bytes(b"")
    (root / "VOL.0").write_bytes(volume)
    # A single dictionary entry: "open", group10, indexed by its first letter.
    alphabet = bytearray(52)
    alphabet[28:30] = (52).to_bytes(2, "big")
    word = bytearray(letter ^ 0x7f for letter in b"open")
    word[-1] |= 0x80
    (root / "WORDS.TOK").write_bytes(alphabet + b"\0" + word + b"\0\x0a")
    # One inventory object with encoded initial room7, independent of live state.
    plain = b"\x03\0\x01\x03\0\x07Authored token\0"
    (root / "OBJECT").write_bytes(bytes(value ^ b"Avis Durgan"[i % 11]
                                       for i, value in enumerate(plain)))
    return root


def _aliased_messages(count=255, length=4096):
    """Many legal slots reference one string; ciphertext is stored only once."""
    raw = b"A" * length + b"\0"
    offset = 2 + 2 * count
    section = (bytes([count]) + (offset + len(raw)).to_bytes(2, "little")
               + offset.to_bytes(2, "little") * count)
    cipher = bytes(value ^ b"Avis Durgan"[i % 11] for i, value in enumerate(raw))
    return b"\x01\0\0" + section + cipher


def _without_auxiliary(root):
    for name in ("WORDS.TOK", "OBJECT"):
        (root / name).unlink()
    return root


@pytest.fixture
def private_directory():
    # The surrounding /workspace checkout itself has a .git ancestor.
    # Keep private generated reports outside all repository trees.
    with tempfile.TemporaryDirectory(prefix="dotbox-agi-test-", dir="/tmp") as path:
        yield Path(path)


def _inspect(root, **options):
    return inspect_scenes(root, profile="2.917", **options)


def test_census_retains_flag_sites_variable_use_and_typed_room_candidate(tmp_path):
    game = _bundle(tmp_path / "game")
    report = _inspect(game, include_ir=True)
    logic = report["logics"][0]
    assert report["format"] == "fdisbull-agi-scene-census-1"
    assert report["qualification"] == "static_scene_candidates_only"
    assert report["executable"] is False
    assert report["coverage"]["accepted_uil_interactions"] == 0
    assert logic["elements"]["state_change_sites"] == [2, 5, 8, 16]
    operations = logic["ir"]["instructions"]
    assert [(row["operation"], row["operands"]) for row in operations[:3]] == [
        ("assignn", [30, 7]), ("assignv", [31, 30]), ("set", [42])]
    assert operations[4]["operation"] == "reset"
    assert logic["conditions"][0]["ordered_tokens"] == [
        {"offset": 11, "opcode": 7, "operation": "isset", "operands": [42]}]
    assert logic["conditions"][0]["successors"] == [
        {"kind": "true", "offset": 16}, {"kind": "false", "offset": 20}]
    reference = logic["references"][0]
    assert reference["operation"] == "new.room.v"
    assert reference["target"] == {"kind": "room", "operand": 31, "mode": "variable",
                                   "variable": 31, "values": [7], "resolution": "finite_set"}
    assert reference["resource_status"] == [{"number": 7, "status": "ok"}]
    assert report["scenes"][0]["logic_binding"] == "requires_qualified_room_dispatch"
    assert report["inventory"]["objects"] == [{"number": 0, "initial_room": 7}]
    assert report["vocabulary"]["literal_entries_included"] is False
    assert "Authored fixture message" not in json.dumps(report)
    assert report["source"]["read_counts"]["VOL.0"] == 1


def test_outline_retains_unknown_targets_and_text_is_explicit(tmp_path):
    game = _bundle(tmp_path / "game")
    report = _inspect(game, stage="outline", include_text=True)
    target = report["logics"][0]["references"][0]["target"]
    assert target["values"] is None and target["reason"] == "outline_stage"
    assert report["coverage"]["value_analysis_complete"] is False
    assert report["logics"][0]["messages"][0]["text"] == "Authored fixture message"
    assert report["inventory"]["objects"][0] == {
        "number": 0, "name": "Authored token", "initial_room": 7}
    assert report["vocabulary"]["groups"][0]["words"] == ["open"]


def test_condition_order_not_or_and_stateful_said_are_preserved(tmp_path):
    # NOT f43, then (f42 OR said(group10)); no branch is evaluated as live truth.
    code = bytes.fromhex("ff fd072b fc072a 0e010a00 fc ff0000 00")
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(code)}))
    logic = report["logics"][0]
    tokens = logic["conditions"][0]["ordered_tokens"]
    assert [token.get("marker", token.get("operation")) for token in tokens] == [
        "not", "isset", "or", "isset", "said", "or"]
    assert tokens[4]["stateful"] is True
    assert tokens[4]["word_groups"] == [10]
    assert logic["command_patterns"][0]["evaluation"] == "ordered_stateful_test"
    assert logic["command_patterns"][0]["qualification"] == "low_level_ir"


def test_local_branch_values_join_without_claiming_which_flag_branch_runs(tmp_path):
    # Unknown f42 selects v30=7 or9. Both paths converge at new.room.v(v30).
    code = bytes.fromhex("ff072aff0600 031e07 fe0300 031e09 131e 00")
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(code)}))
    assert report["logics"][0]["references"][0]["target"]["values"] == [7, 9]
    assert report["coverage"]["value_analysis_complete"] is True


@pytest.mark.parametrize("code", [
    "ff072aff0300 031e07 131e 00",  # One predecessor never assigned v30.
    "030b07 130b 00",              # v11 is an engine-owned clock variable.
    "031e07 1601 131e 00",         # A call can change values.
    "031e07 0b5a09 131e 00",       # An unknown indirect write can alias v30.
])
def test_unknown_or_volatile_values_do_not_become_room_facts(tmp_path, code):
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(bytes.fromhex(code))}))
    target = next(reference["target"] for reference in report["logics"][0]["references"]
                  if reference["target"]["kind"] == "room")
    assert target["values"] is None
    assert target["reason"] == "unknown_reaching_value"


def test_signed_backward_goto_has_an_instruction_boundary_target(tmp_path):
    code = bytes.fromhex("011e fefbff")  # increment v30; goto the increment.
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(code)}), include_ir=True)
    logic = report["logics"][0]
    assert logic["status"] == "decoded"
    assert logic["ir"]["instructions"][1]["successors"] == [{"kind": "branch", "offset": 2}]


def test_high_bit_if_is_unqualified_even_when_signed_target_is_a_boundary(tmp_path):
    code = bytes.fromhex("ff0700fffaff 00")  # Signed interpretation would jump back to IF.
    with pytest.raises(ValueError, match="[Uu]nqualified.*IF|IF.*unqualified"):
        logic_layout(_payload(code))
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(code), 1: _payload(b"\0")}))
    assert report["logics"][0]["status"] == "layout_error"
    assert report["logics"][0]["opaque_resource"] is True
    assert report["logics"][0]["references"] == []
    assert report["logics"][1]["status"] == "decoded"
    assert report["coverage"]["logic_layout_complete"] is False


@pytest.mark.parametrize("code", [
    "feffff 00",                  # GOTO into its displacement operand.
    "ff072aff0100 031e07 00",     # IF into an assignn operand.
    "031e",                      # Truncated assignn.
    "ae 00",                     # Outside the2.917 action range.
    "95 00",                     # Context-dependent trace.on layout.
])
def test_bad_or_unqualified_logic_remains_opaque(tmp_path, code):
    report = _inspect(_bundle(tmp_path / "game", {0: _payload(bytes.fromhex(code))}))
    assert report["logics"][0]["status"] == "layout_error"
    assert report["logics"][0]["opaque_resource"] is True
    assert report["coverage"]["decoded_logics"] == 0


def test_resource_failure_is_retained_without_discarding_good_logic(tmp_path):
    game = _bundle(tmp_path / "game", {0: _payload(b"\0"), 1: _payload(b"\0")})
    volume = bytearray((game / "VOL.0").read_bytes())
    volume[0:2] = b"NO"
    (game / "VOL.0").write_bytes(volume)
    report = _inspect(game)
    assert [row["status"] for row in report["logics"]] == ["resource_error", "decoded"]
    assert report["resource_issues"][0]["error"] == "Invalid v2 resource signature"
    assert report["coverage"]["resource_integrity_complete"] is False
    assert report["source"]["read_counts"]["VOL.0"] == 1


def test_malformed_directory_and_message_table_report_their_own_scope(tmp_path):
    game = _bundle(tmp_path / "game", {0: _payload(b"\0")[:-1]})
    (game / "PICDIR").write_bytes(b"x")
    report = _inspect(game)
    assert report["coverage"]["resource_census_complete"] is False
    assert report["logics"][0]["status"] == "decoded"
    assert report["logics"][0]["message_status"] == "error"
    assert report["coverage"]["message_errors"] == 1


@pytest.mark.parametrize("budget", [{"max_instructions": 1}, {"max_code_bytes": 1}])
def test_global_layout_budgets_stop_whole_logics(tmp_path, budget):
    report = _inspect(_bundle(tmp_path / "game"), **budget)
    assert report["logics"][0]["status"] == "instruction_budget"
    assert report["logics"][0]["opaque_resource"] is True
    # A rejected parse still consumed its attempted instruction. A code-span
    # preflight rejection, however, leaves room for a later tiny resource.
    assert report["logics"][1]["status"] == ("instruction_budget" if "max_instructions" in budget else "decoded")
    assert report["coverage"]["logic_layout_complete"] is False


def test_oversized_declared_code_is_rejected_before_layout(monkeypatch):
    from dotbox import agi_scenes

    def forbidden(*args, **kwargs):
        pytest.fail("Layout scanned a resource that its declared code span already excludes")

    monkeypatch.setattr(agi_scenes, "logic_layout", forbidden)
    with pytest.raises(ValueError, match="code-byte"):
        agi_scenes._decode(_payload(b"\0" * 60000), 1, 1)


def test_layout_stops_before_the_next_instruction_record():
    work = {}
    with pytest.raises(ValueError, match="instruction budget"):
        logic_layout(_payload(b"\0" * 60000), max_instructions=1, usage=work)
    assert work["instructions_attempted"] == 1


def test_rejected_layout_work_consumes_global_budget(tmp_path):
    game = _bundle(tmp_path / "game", {0: _payload(b"\0\xae"), 1: _payload(b"\0")})
    report = _inspect(game, max_instructions=2)
    assert [row["status"] for row in report["logics"]] == ["layout_error", "instruction_budget"]
    assert report["coverage"]["instructions_attempted"] == 2
    assert report["coverage"]["code_bytes_admitted"] == 2
    assert report["coverage"]["instructions"] == 0


def test_message_expansion_is_refused_before_text_hashing(tmp_path, monkeypatch):
    from dotbox import agi_resources

    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _aliased_messages()}))
    original = agi_resources.sha256

    def observed(data=b""):
        assert data != b"A" * 4096, "An over-budget message was copied/decrypted for hashing"
        return original(data)

    monkeypatch.setattr(agi_resources, "sha256", observed)
    report = _inspect(game, include_text=True, max_instructions=1, max_code_bytes=1,
                      max_updates=1, max_message_bytes=128)
    assert report["logics"][0]["message_status"] == "budget"
    assert report["logics"][0]["messages"] == []
    assert report["coverage"]["message_budget_stops"] == 1
    assert report["coverage"]["expanded_text_bytes"] == 0


def test_aliases_reuse_decoding_but_text_occurrences_consume_global_budget(tmp_path, monkeypatch):
    from dotbox import agi_resources

    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _aliased_messages(2, 4)}))
    (game / "LOGDIR").write_bytes(b"\0\0\0" * 2)
    original, hashes = agi_resources.sha256, []

    def observed(data=b""):
        if data == b"AAAA":
            hashes.append(data)
        return original(data)

    monkeypatch.setattr(agi_resources, "sha256", observed)
    report = _inspect(game, include_text=True, max_message_bytes=12,
                      max_instructions=1, max_code_bytes=1)
    assert [row["status"] for row in report["logics"]] == ["decoded", "decoded"]
    assert [row["message_status"] for row in report["logics"]] == ["decoded", "budget"]
    assert [len(row["messages"]) for row in report["logics"]] == [2, 1]
    assert report["coverage"]["instructions_attempted"] == 1
    assert report["coverage"]["code_bytes_admitted"] == 1
    assert report["coverage"]["logic_aliases"] == 1
    assert report["coverage"]["expanded_text_bytes"] == 12
    assert report["coverage"]["unique_text_bytes"] == 4
    assert len(hashes) == 1


def test_metadata_only_aliases_hash_unique_bytes_without_literal_expansion(tmp_path, monkeypatch):
    from dotbox import agi_resources

    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _aliased_messages(255, 4096)}))
    (game / "LOGDIR").write_bytes(b"\0\0\0" * 2)
    original, hashes = agi_resources.sha256, []

    def observed(data=b""):
        if data == b"A" * 4096:
            hashes.append(data)
        return original(data)

    monkeypatch.setattr(agi_resources, "sha256", observed)
    report = _inspect(game, max_message_bytes=4096, max_instructions=1, max_code_bytes=1)
    assert all(row["message_status"] == "decoded" for row in report["logics"])
    assert report["coverage"]["expanded_text_bytes"] == 4096
    assert report["coverage"]["unique_text_bytes"] == 4096
    assert report["coverage"]["text_cache_hits"] == 509
    assert len(hashes) == 1
    assert all("text" not in message for row in report["logics"] for message in row["messages"])


def test_message_aliases_preserve_suffix_offsets_and_cipher_phase():
    raw = b"abcde\0"
    # First pointer starts at the shared string area; second starts two bytes in.
    table = b"\x02\x0c\0\x06\0\x08\0"
    cipher = bytes(value ^ b"Avis Durgan"[i % 11] for i, value in enumerate(raw))
    messages = logic_messages(b"\x01\0\0" + table + cipher, max_message_bytes=8)
    assert [row["text"] for row in messages] == ["abcde", "cde"]
    assert [row["length"] for row in messages] == [5, 3]
    assert [row["offset"] for row in messages] == [10, 12]


def test_inventory_name_aliases_share_the_text_budget(tmp_path):
    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _payload(b"\0")}))
    plain = b"\x06\0\x01" + b"\x06\0\x07" * 2 + b"A" * 4096 + b"\0"
    (game / "OBJECT").write_bytes(bytes(value ^ b"Avis Durgan"[i % 11]
                                        for i, value in enumerate(plain)))
    report = _inspect(game, include_text=True, max_message_bytes=4096)
    assert report["inventory"]["status"] == "budget"
    assert report["coverage"]["expanded_text_bytes"] == 4096
    assert report["coverage"]["unique_text_bytes"] == 4096
    assert report["logics"][0]["status"] == "decoded"


def test_auxiliary_rejected_text_work_remains_charged_and_metadata_omits_names(tmp_path):
    game = _bundle(tmp_path / "game", {0: _aliased_messages(1, 1)})
    # WORDS.TOK is read first. Constructing its indexed "open" with literal text
    # needs two report occurrences; after one letter the next admission fails.
    report = _inspect(game, include_text=True, max_message_bytes=2)
    assert report["vocabulary"]["status"] == "budget"
    assert report["inventory"]["status"] == "budget"
    assert report["logics"][0]["message_status"] == "budget"
    assert report["coverage"]["expanded_text_bytes"] == 2
    assert report["coverage"]["auxiliary_text_budget_stops"] == 2
    (game / "WORDS.TOK").unlink()
    report = _inspect(game, include_text=False, max_message_bytes=1)
    assert report["inventory"]["status"] == "decoded"
    assert report["inventory"]["objects"] == [{"number": 0, "initial_room": 7}]
    assert report["logics"][0]["message_status"] == "decoded"


def test_report_budget_uses_incremental_encoding_before_full_json_dump(tmp_path, monkeypatch):
    from dotbox import agi_scenes

    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _payload(b"\0" * 1000)}))

    def forbidden(*args, **kwargs):
        pytest.fail("An unbounded json.dumps ran before report budget enforcement")

    monkeypatch.setattr(agi_scenes.json, "dumps", forbidden)
    with pytest.raises(ValueError, match="report.*budget|budget.*report"):
        _inspect(game, include_ir=True, max_report_bytes=16384)


def test_report_budget_failure_creates_no_output(tmp_path, private_directory, capsys):
    from dotbox.agi import main

    game = _without_auxiliary(_bundle(tmp_path / "game", {0: _payload(b"\0" * 1000)}))
    output = private_directory / "report.json"
    assert main(["inspect", str(game), "--profile", "2.917", "--include-ir",
                 "--max-report-bytes", "16384", "--output", str(output)]) == 1
    assert "budget" in json.loads(capsys.readouterr().err)["error"]
    assert not output.exists()


def test_report_limit_counts_escaped_bytes_and_final_newline():
    from dotbox.agi_scenes import serialize_report

    limit = 16384
    # Compact syntax + newline adds twelve bytes; each non-ASCII char needs six.
    value = {"text": "é" * ((limit - 12) // 6)}
    raw = serialize_report(value, limit)
    assert raw.endswith(b"\n") and len(raw) <= limit
    value["text"] += "é"
    with pytest.raises(ValueError, match="report byte budget"):
        serialize_report(value, limit)


def test_new_budget_ranges_are_documented_in_cli_help(capsys):
    from dotbox.agi import main

    with pytest.raises(SystemExit) as result:
        main(["inspect", "--help"])
    assert result.value.code == 0
    text = capsys.readouterr().out
    for value in ("--max-message-bytes", "--max-report-bytes", "1..4194304", "16384..16777216",
                  "1..2000000", "1..1000000"):
        assert value in text


@pytest.mark.parametrize("argument,value", [
    ("max_message_bytes", 0), ("max_message_bytes", 4194305), ("max_message_bytes", True),
    ("max_report_bytes", 16383), ("max_report_bytes", 16777217), ("max_report_bytes", True),
])
def test_new_budget_ranges_are_validated_before_resource_reads(tmp_path, monkeypatch, argument, value):
    from dotbox import agi_scenes

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid budget read resources")

    monkeypatch.setattr(agi_scenes, "V2Resources", forbidden)
    with pytest.raises(ValueError, match=argument):
        _inspect(tmp_path / "unread", **{argument: value})


def test_unfinished_value_analysis_does_not_publish_intermediate_constants(tmp_path):
    report = _inspect(_bundle(tmp_path / "game"), max_updates=1)
    target = report["logics"][0]["references"][0]["target"]
    assert target["values"] is None and target["reason"] == "analysis_budget"
    assert report["coverage"]["value_analysis_complete"] is False


def test_resource_snapshot_and_message_decode_do_not_read_again(tmp_path):
    game = _bundle(tmp_path / "game")
    resources = V2Resources(game)
    rows = resources.resources("logic")
    (game / "VOL.0").write_bytes(b"changed after snapshot")
    assert resources.resources("logic") == rows
    assert resources.manifest()["read_counts"]["VOL.0"] == 1
    assert logic_messages(rows[0]["payload"])[0]["text"] == "Authored fixture message"


def test_cli_writes_new_private_report_and_only_summary_to_stdout(tmp_path, private_directory, capsys):
    from dotbox.agi import main

    game = _bundle(tmp_path / "game")
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in game.iterdir()}
    output = private_directory / "report.json"
    assert main(["inspect", str(game), "--profile", "2.917", "--stage", "outline",
                 "--include-text", "--include-ir", "--output", str(output)]) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured.err == ""
    assert summary["ok"] is True
    assert summary["qualified_interactions"] == 0
    assert summary["executable"] is False
    assert summary["limits"] and summary["limitations"]
    assert "Authored fixture message" not in captured.out
    assert "Authored token" not in captured.out
    raw = output.read_bytes()
    report = json.loads(raw)
    assert report["format"] == "fdisbull-agi-scene-census-1"
    assert report["logics"][0]["messages"][0]["text"] == "Authored fixture message"
    assert summary["report"]["sha256"] == sha256(raw).hexdigest()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert before == {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in game.iterdir()}


@pytest.mark.parametrize("kind", ["existing", "public_parent", "git_dir", "git_file", "bare_git",
                                  "symlink_file", "symlink_parent", "inside_input"])
def test_cli_refuses_unsafe_report_destinations(tmp_path, private_directory, capsys, kind):
    from dotbox.agi import main

    game = _bundle(tmp_path / "game")
    parent = private_directory / "destination"
    parent.mkdir(mode=0o700)
    output = parent / "report.json"
    sentinel = private_directory / "sentinel"
    sentinel.write_text("preserve")
    if kind == "existing":
        output.write_text("preserve")
    elif kind == "public_parent":
        parent.chmod(0o755)
    elif kind == "git_dir":
        (private_directory / ".git").mkdir()
    elif kind == "git_file":
        (private_directory / ".git").write_text("gitdir: elsewhere\n")
    elif kind == "bare_git":
        (private_directory / "HEAD").write_text("ref: refs/heads/main\n")
        (private_directory / "objects").mkdir()
        (private_directory / "refs").mkdir()
    elif kind == "symlink_file":
        output.symlink_to(sentinel)
    elif kind == "symlink_parent":
        alias = private_directory / "alias"
        alias.symlink_to(parent, target_is_directory=True)
        output = alias / "report.json"
    elif kind == "inside_input":
        output = game / "report.json"
    assert main(["inspect", str(game), "--profile", "2.917", "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["ok"] is False
    assert sentinel.read_text() == "preserve"
    if kind == "existing":
        assert output.read_text() == "preserve"
    elif kind != "symlink_file":
        assert not output.exists()


@pytest.mark.parametrize("arguments", [
    [], ["--profile", "3.002"], ["--stage", "full"], ["--max-updates", "0"],
    ["--max-instructions", "1000001"], ["--max-code-bytes", "4194305"],
])
def test_cli_requires_explicit_profile_output_and_valid_existing_budgets(
        tmp_path, private_directory, capsys, arguments):
    from dotbox.agi import main

    game = _bundle(tmp_path / "game")
    output = private_directory / "report.json"
    if arguments:
        arguments = ["--profile", "2.917", "--output", str(output), *arguments]
    assert main(["inspect", str(game), *arguments]) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert not output.exists()


def test_doctor_check_runs_authored_bytes_without_fdisbull_or_native_imports():
    source = Path(__file__).resolve().parents[1] / "src"
    program = """
import json, sys
sys.path.insert(0, sys.argv[1])
from dotbox.agi import self_check
result = self_check()
assert not any(name == 'fdisbull' or name.startswith('fdisbull.') for name in sys.modules)
assert not any(name in sys.modules for name in ('dotbox.backend', 'dotbox.native_rpc'))
print(json.dumps(result))
"""
    process = subprocess.run([sys.executable, "-I", "-c", program, str(source)],
                             check=True, capture_output=True, text=True)
    result = json.loads(process.stdout)
    assert result["ok"] is True
    assert result["qualified_interactions"] == 0
    assert result["checks"] and all(result["checks"].values())
