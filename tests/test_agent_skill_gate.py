"""The release gate follows the installed skill index and authenticates its files."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import venv

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_agent_skill", ROOT / "scripts" / "check_agent_skill.py"
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


@pytest.mark.parametrize('lookup',['relative_path','relative_path_entry'])
def test_relative_interpreter_keeps_virtualenv_from_another_working_directory(tmp_path,monkeypatch,lookup):
    environment=tmp_path/'.native/offline/installed'
    venv.EnvBuilder(with_pip=False,symlinks=os.name!='nt').create(environment)
    relative=Path('.native/offline/installed')/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    monkeypatch.chdir(tmp_path)
    if lookup=='relative_path_entry':
        monkeypatch.setenv('PATH',str(relative.parent))
        requested=relative.name
    else:requested=str(relative)
    executable=gate._interpreter_executable(requested)
    raw,code=gate.run_bounded([executable,'-I','-c',
                              'import json,sys;print(json.dumps({"prefix":sys.prefix,"executable":sys.executable}))'],
                             timeout=5,output_limit=4096)
    identity=json.loads(raw)
    assert code==0 and Path(identity['prefix'])==environment
    assert Path(identity['executable'])==tmp_path/relative


def good_bundle():
    index = {
        "name": "fdisbull-investigate",
        "format": "fdisbull-skill-index-1",
        "entrypoint": "SKILL.md",
        "guides": [
            {"reference": "SKILL.md", "purpose": "Start with the investigation method"},
            {"reference": "references/workflows.md", "purpose": "Choose an investigation workflow"},
        ],
    }
    documents = {
        "SKILL.md": (
            "---\nname: fdisbull-investigate\n"
            "description: Investigate supported program evidence.\n---\n"
            "Read [workflows](references/workflows.md).\n"
            "Example only: ` [not a link](references/missing.md) `.\n"
            "```md\n[also not a link](../outside.md)\n```\n"
            "External [reference](https://example.invalid/guide.md).\n"
        ),
        "references/workflows.md": "# Workflows\nChoose a bounded next step.\n",
    }
    return index, documents


def test_index_reads_only_indexed_resources_and_checks_local_links():
    index, documents = good_bundle()
    calls = []

    def read(reference):
        calls.append(reference)
        return documents[reference]

    result = gate.verify_index(index, read)
    assert calls == ["SKILL.md", "references/workflows.md"]
    assert result["skill_name"] == "fdisbull-investigate"
    assert result["reference_count"] == 2
    assert result["local_markdown_link_count"] == 1
    assert result["files"][0]["local_markdown_links"] == ["references/workflows.md"]
    assert all("text" not in row for row in result["files"])


def test_missing_index_reference_for_local_link_is_rejected():
    index, documents = good_bundle()
    index["guides"] = index["guides"][:1]
    with pytest.raises(gate.GateError, match="missing from the skill index"):
        gate.verify_index(index, documents.__getitem__)


def test_indexed_but_unavailable_reference_is_rejected():
    index, documents = good_bundle()
    del documents["references/workflows.md"]
    with pytest.raises(gate.GateError, match="selective read failed"):
        gate.verify_index(index, documents.__getitem__)


@pytest.mark.parametrize("mutation, message", [
    (lambda index: index["guides"].append(dict(index["guides"][0])), "duplicate indexed reference"),
    (lambda index: index.update(entrypoint="references/../SKILL.md"), "normalized relative path"),
    (lambda index: index.update(name="other-skill"), "must be fdisbull-investigate"),
])
def test_duplicate_unsafe_or_wrong_skill_index_is_rejected(mutation, message):
    index, documents = good_bundle()
    mutation(index)
    with pytest.raises(gate.GateError, match=message):
        gate.verify_index(index, documents.__getitem__)


@pytest.mark.parametrize("purpose", ["", " \n ", "x" * 2049])
def test_missing_or_unbounded_guide_purpose_is_rejected(purpose):
    index, documents = good_bundle()
    index["guides"][1]["purpose"] = purpose
    with pytest.raises(gate.GateError, match="purpose"):
        gate.verify_index(index, documents.__getitem__)


@pytest.mark.parametrize("frontmatter", [
    "---\nname: fdisbull-investigate\n---\n",
    "---\nname: other-skill\ndescription: Present.\n---\n",
    "---\nname: fdisbull-investigate\ndescription: null\n---\n",
    "---\nname: fdisbull-investigate\nname: duplicate\ndescription: Present.\n---\n",
])
def test_missing_mismatched_or_duplicate_skill_metadata_is_rejected(frontmatter):
    index, documents = good_bundle()
    documents["SKILL.md"] = frontmatter
    with pytest.raises(gate.GateError):
        gate.verify_index(index, documents.__getitem__)


def test_local_markdown_link_cannot_escape_skill_root():
    index, documents = good_bundle()
    documents["SKILL.md"] = (
        "---\nname: fdisbull-investigate\ndescription: Present.\n---\n"
        "[escape](../outside.md)\n"
    )
    with pytest.raises(gate.GateError, match="escapes the skill directory"):
        gate.verify_index(index, documents.__getitem__)


def test_duplicate_local_markdown_link_is_rejected():
    index, documents = good_bundle()
    documents["SKILL.md"] = (
        "---\nname: fdisbull-investigate\ndescription: Present.\n---\n"
        "[workflow](references/workflows.md) and [again](references/workflows.md).\n"
    )
    with pytest.raises(gate.GateError, match="duplicate local Markdown link"):
        gate.verify_index(index, documents.__getitem__)


def test_bounded_subprocess_stops_at_output_cap_without_returning_payload():
    command = [sys.executable, "-I", "-c",
               "import sys; sys.stdout.buffer.write(b'x' * 500000); sys.stdout.flush()"]
    started = time.monotonic()
    with pytest.raises(gate.GateError, match="output limit"):
        gate.run_bounded(command, timeout=3, output_limit=4096)
    assert time.monotonic() - started < 3


def test_bounded_subprocess_enforces_deadline():
    command = [sys.executable, "-I", "-c", "import time; time.sleep(30)"]
    started = time.monotonic()
    with pytest.raises(gate.GateError, match="timed out"):
        gate.run_bounded(command, timeout=0.1, output_limit=4096)
    assert time.monotonic() - started < 3


def test_receipt_is_private_non_overwriting_and_outside_checkout(tmp_path):
    receipt = tmp_path / "receipt.json"
    gate._write_receipt(receipt, {"status": "passed"})
    assert json.loads(receipt.read_text()) == {"status": "passed"}
    with pytest.raises(gate.GateError, match="already exists"):
        gate._write_receipt(receipt, {"status": "replace"})
    with pytest.raises(gate.GateError, match="outside the repository"):
        gate._write_receipt(ROOT / "receipt.json", {"status": "forbidden"})
