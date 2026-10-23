"""DOS view behavior over real SQLite storage and independently supplied facts."""
import json

import pytest

from fdisbull.dos_views import DOSViewsMixin
from fdisbull.project import Project

A, B, GLOBAL = "x86:16:little:cs=0010", "x86:16:little:cs=0011", "x86:16:little"


def key(address):
    return f"{address:016x}"


class Views(DOSViewsMixin):
    """Exercise the standalone view mixin over a real Project, without routing."""
    def __init__(self, project):
        self.project = project

    def __getattr__(self, name):
        return getattr(self.project, name)


@pytest.fixture
def stored(tmp_path):
    source = tmp_path / "view.bin"
    source.write_bytes(bytes(96))
    project = Project.create(tmp_path / "views.fdb", source, arch="x86", bits=16, base=0x100)
    project.meta["entry"] = 0x110
    project.db.executescript("""
    CREATE TABLE IF NOT EXISTS dos_segments(version INTEGER,selector INTEGER,base TEXT,end TEXT,roles TEXT,sources TEXT,PRIMARY KEY(version,selector));
    CREATE TABLE IF NOT EXISTS dos_edges(version INTEGER,source_context TEXT,source TEXT,target TEXT,target_context TEXT,kind TEXT,evidence TEXT,PRIMARY KEY(version,source_context,source,target,target_context,kind));
    CREATE TABLE IF NOT EXISTS dos_states(version INTEGER,context TEXT,address TEXT,registers TEXT,state TEXT,reason TEXT,PRIMARY KEY(version,context,address));
    """)
    for table in ("instructions", "functions", "xrefs", "operand_refs", "annotations", "definitions", "data_items", "dos_segments", "dos_edges", "dos_states"):
        project.db.execute(f"DELETE FROM {table}")
    facts = [(A, 0x110, 3, "a13000", "mov", "ax,[0030h]", "next", None),
             (A, 0x113, 3, "e80a00", "call", "0020h", "call", key(0x120)),
             (A, 0x116, 1, "c3", "ret", "", "return", None),
             (A, 0x120, 1, "c3", "ret", "", "return", None),
             (B, 0x110, 3, "a13000", "mov", "ax,[0030h]", "next", None)]
    for context, address, size, raw, mnemonic, operands, flow, target in facts:
        project.db.execute("INSERT INTO instructions VALUES (?,?,?,?,?,?,?,?,?)", (1, context, key(address), size, raw, mnemonic, operands, flow, target))
    for context, address, name in [(A, 0x110, "entry_a"), (B, 0x110, "entry_b"), (A, 0x120, "helper")]:
        project.db.execute("INSERT INTO functions VALUES (?,?,?,?,?,?)", (1, context, key(address), name, "test observed decode", "candidate"))
    for source, target, target_context, kind in [(0x113, 0x120, A, "call"), (0x110, 0x130, "", "data")]:
        project.db.execute("INSERT INTO dos_edges VALUES (?,?,?,?,?,?,?)", (1, A, key(source), key(target), target_context, kind, "stored fixture reference"))
        project.db.execute("INSERT INTO xrefs VALUES (?,?,?,?,?,?)", (1, A, key(source), key(target), kind, "stored fixture reference"))
    project.db.execute("INSERT INTO operand_refs VALUES (?,?,?,?,?,?,?)", (1, A, key(0x110), 1, "memory", key(0x130), 2))
    project.db.execute("INSERT INTO operand_refs VALUES (?,?,?,?,?,?,?)", (1, A, key(0x113), 0, "branch", key(0x120), 2))
    project.db.execute("INSERT INTO definitions VALUES (?,?,?,?,?,?)", (1, GLOBAL, key(0x130), "u16", 2, "TiGa"))
    project.db.execute("INSERT INTO annotations VALUES (?,?,?,?,?,?,?,NULL)", (1, GLOBAL, key(0x130), "name", "counter", "TiGa", "fixture"))
    project.db.execute("INSERT INTO annotations VALUES (?,?,?,?,?,?,?,NULL)", (1, GLOBAL, key(0x110), "comment", "DS is inferred", "TiGa", "fixture"))
    project.db.execute("INSERT INTO dos_states VALUES (?,?,?,?,?,?)", (1, A, key(0x110), json.dumps({"ds": 0x10}), "decoded", "initial abstract state"))
    for selector in (0x10, 0x11):
        project.db.execute("INSERT INTO dos_segments VALUES (?,?,?,?,?,?)", (1, selector, key(selector * 16), key(0x160), json.dumps(["candidate"]), json.dumps([{"kind": "fixture evidence"}])))
    project.db.commit()
    yield project, Views(project)
    project.db.close()


def test_segmented_parser_preserves_physical_alias_identity(stored):
    _, views = stored
    assert views._dos_parse_address("0010:0010") == (0x110, 0x10)
    assert views._dos_parse_address("0011:0000") == (0x110, 0x11)
    assert views._dos_parse_address("0x110") == (0x110, None)
    assert views._dos_parse_address(0x110, cs="0010") == (0x110, 0x10)
    with pytest.raises(ValueError, match="conflicts"):
        views._dos_parse_address("0010:0010", cs=0x11)
    with pytest.raises(ValueError, match="1 MiB"):
        views._dos_parse_address("ffff:ffff")
    with pytest.raises(ValueError, match="16-bit"):
        views._dos_parse_address("10000:0000")


def test_linear_disassembly_reports_aliases_and_explicit_cs_selects_exactly(stored):
    _, views = stored
    snapshot = views._dos_disassembly(0x110)
    assert snapshot["context"] == A and snapshot["alternative_contexts"] == [B]
    assert any("aliases" in message for message in snapshot["warnings"])
    assert [item["address"] for item in snapshot["instructions"]] == ["0x110", "0x113", "0x116", "0x120"]
    row = snapshot["instructions"][0]
    assert (row["cs"], row["ip"], row["segmented_address"]) == (0x10, 0x10, "0010:0010")
    explicit = views._dos_disassembly("0011:0000")
    assert explicit["context"] == B and len(explicit["instructions"]) == 1
    assert explicit["instructions"][0]["name"] == "entry_b"
    assert explicit["instructions"][0]["ip"] == 0


def test_disassembly_uses_global_representation_and_keeps_raw_evidence(stored):
    _, views = stored
    row = views._dos_disassembly("0010:0010")["instructions"][0]
    assert row["raw_operands"] == row["operands"] == "ax,[0030h]"
    assert row["display_operands"] == "ax,[0030h] ; counter <u16>"
    assert row["references"][0]["name"] == "counter"
    assert row["references"][0]["representation"] == "u16"
    assert row["comment"] == "DS is inferred" and row["comment_author"] == "TiGa"
    assert row["assumptions"] == {"registers": {"ds": 0x10}, "state": "decoded", "reason": "initial abstract state"}


def test_global_rename_propagates_across_alias_functions_and_xrefs(stored):
    project, views = stored
    project.annotate(0x110, "shared_entry", kind="name", author="TiGa")
    aliases = [item for item in views._dos_functions() if item["address"] == "0x110"]
    assert len(aliases) == 2 and {item["name"] for item in aliases} == {"shared_entry"}
    assert views._dos_disassembly("0011:0000")["instructions"][0]["name"] == "shared_entry"
    project.annotate(0x130, "renamed_counter", kind="name", author="TiGa")
    assert "renamed_counter <u16>" in views._dos_disassembly("0010:0010")["instructions"][0]["display_operands"]
    assert views._dos_xrefs(0x130)[0]["target_name"] == "renamed_counter"


def test_xrefs_keep_context_and_deduplicate_richer_edges(stored):
    project, views = stored
    incoming = views._dos_xrefs("0010:0020")
    assert len(incoming) == 1 and incoming[0]["source_segmented_address"] == "0010:0013"
    assert incoming[0]["target_segmented_address"] == "0010:0020"
    assert views._dos_xrefs("0011:0010") == []  # same physical target, different CS interpretation
    assert views._dos_xrefs(0x130, cs=0x11)[0]["kind"] == "data"  # shared physical data
    project.db.execute("INSERT INTO xrefs VALUES (?,?,?,?,?,?)", (1, B, key(0x110), key(0x121), "call", "legacy edge"))
    fallback = views._dos_xrefs(0x121)
    assert len(fallback) == 1 and fallback[0]["target_context"] is None
    assert views._dos_xrefs(0x110, "from", cs=0x11)[0]["evidence"] == "legacy edge"


def test_segment_inventory_preserves_provenance_without_claiming_whole_code(stored):
    _, views = stored
    inventory = views._dos_segments()
    assert [item["instruction_count"] for item in inventory] == [4, 1]
    assert all(item["bounds_inferred"] for item in inventory)
    assert inventory[0]["roles"] == ["candidate"]
    assert inventory[0]["sources"] == [{"kind": "fixture evidence"}]
    assert all("candidate" in item["classification"] for item in inventory)


def test_code_regions_are_contiguous_runs_per_cs_not_segment_extents(stored):
    _, views = stored
    regions = views._dos_regions()
    assert [(item["context"], item["start"], item["end"], item["instruction_count"]) for item in regions] == [
        (A, "0x110", "0x117", 3), (A, "0x120", "0x121", 1), (B, "0x110", "0x113", 1)]
    assert regions[0]["start_segmented"] == "0010:0010" and regions[0]["end_segmented"] == "0010:0017"
    assert all(item["end_exclusive"] for item in regions)


def test_nearest_stored_address_and_validation_do_not_decode_new_facts(stored):
    project, views = stored
    count = project.db.execute("SELECT count(*) FROM instructions").fetchone()[0]
    snapshot = views._dos_disassembly(0x11F)
    assert snapshot["view_start"] == "0x120" and snapshot["warnings"]
    assert project.db.execute("SELECT count(*) FROM instructions").fetchone()[0] == count
    with pytest.raises(ValueError, match="lines"):
        views._dos_disassembly(lines=0)
    with pytest.raises(ValueError, match="direction"):
        views._dos_xrefs(0x110, direction="sideways")
    assert views._dos_label(1, 0x125, A) == "loc_0010_0025"
    assert views._dos_label(1, 0x125) == "mem_125"


def test_dos_views_and_global_names_survive_database_reopen(stored):
    project, _ = stored
    project.annotate(0x130, "durable_word", kind="name", author="TiGa")
    project.db.commit()
    with Project(project.path) as reopened:
        views = Views(reopened)
        row = views._dos_disassembly("0010:0010")["instructions"][0]
        assert row["references"][0]["name"] == "durable_word"
        assert row["alternative_contexts"] == [B]
        assert len(views._dos_regions()) == 3
        assert views._dos_xrefs("0010:0020")[0]["source_segmented_address"] == "0010:0013"


def test_explicit_cs_never_silently_skips_a_requested_undecoded_byte(stored):
    project, views = stored
    count = project.db.execute('SELECT count(*) FROM instructions').fetchone()[0]
    # This is inside the first stored 3-byte instruction; a later start exists.
    missing = views._dos_disassembly('0010:0011')
    assert missing['address'] == missing['view_start'] == '0x111'
    assert missing['context'] == A and missing['instructions'] == []
    assert any('exact-address view is empty' in warning for warning in missing['warnings'])
    # A physical alias has a row in A but none at this address in B.
    wrong_context = views._dos_disassembly(0x113, cs=0x11)
    assert wrong_context['context'] == B and wrong_context['instructions'] == []
    assert project.db.execute('SELECT count(*) FROM instructions').fetchone()[0] == count
    assert views._dos_disassembly('0010:0013')['instructions'][0]['address'] == '0x113'


def test_disassembly_marks_only_explicit_or_function_labels_for_rendering(stored):
    project, views = stored
    rows = views._dos_disassembly('0010:0010')['instructions']
    assert [(r['address'], r['show_label']) for r in rows] == [
        ('0x110', True), ('0x113', False), ('0x116', False), ('0x120', True)]
    assert rows[1]['name'] == 'loc_0010_0013'  # identity still available to agents
    # Explicit names that look generated must still display.
    project.annotate(0x113, 'loc_user_supplied', kind='name', author='TiGa')
    named = views._dos_disassembly('0010:0013')['instructions'][0]
    assert named['show_label'] and named['name'] == 'loc_user_supplied'
