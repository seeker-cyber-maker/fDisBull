"""Cloud harness guidance is selectively available without a project or guest."""

import json
from importlib.resources import files

from fdisbull.cli import invoke, main, respond


REFERENCE = "references/cloud-harness.md"


def test_cloud_reference_is_discoverable_and_returned_without_a_project(capsys):
    index = invoke("agent-skill", {"index": True})
    guide = next(row for row in index["guides"] if row["reference"] == REFERENCE)
    assert guide["purpose"]
    expected = (files("fdisbull") / "skills" / "fdisbull-investigate" / REFERENCE).read_text(
        encoding="utf-8"
    )
    response = respond(
        {"method": "agent-skill", "params": {"reference": REFERENCE}},
        default_project="/not-a-project",
    )
    assert response["ok"]
    assert response["result"]["files"] == {REFERENCE: expected}
    assert main(["agent-skill", "--reference", REFERENCE]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["files"] == {REFERENCE: expected}
