"""Source-reconstruction guidance stays available through selective skill reads.

These are documentation/discovery checks, not reconstruction or compiler tests.
No external repository, game input, network or toolchain is used.
"""

import re

import pytest

from fdisbull.cli import invoke


REFERENCE = 'references/recovery-research.md'
CIVD_PIN = 'c425f7ba45411111c7c71d926e1ce8d4fa641571'


def read_reference(reference):
    result = invoke('agent-skill', {'reference': reference})
    assert result['name'] == 'fdisbull-investigate'
    assert set(result['files']) == {reference}
    return result['files'][reference]


def test_entrypoint_routes_source_reconstruction_to_existing_reference():
    text = read_reference('SKILL.md')
    assert 'source-reconstruction reuse' in text
    assert text.count(f']({REFERENCE})') == 1
    assert 'independent recovery arm' in text
    index = invoke('agent-skill', {'index': True})
    assert REFERENCE in {row['reference'] for row in index['guides']}


@pytest.mark.parametrize('heading', [
    '## Reuse reconstructed source',
    '### Discover and classify',
    '### Establish correspondence without laundering claims',
    '### Turn results into executable definitions',
    '### Keep three reuse modes measurable',
])
def test_reconstruction_workflow_is_selectively_retrievable(heading):
    text = read_reference(REFERENCE)
    assert heading in text
    assert len(text.encode('utf-8')) < 65536


def test_workflow_retains_evidence_and_import_boundaries():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'upstream-reported', 'input-matched', 'locally-rebuilt',
        'source-bound', 'semantically-qualified',
        'raw linker output and post-link edits separate',
        'not a general importer for arbitrary reconstructed C',
        'source/backing, backing/UIL and UIL/target relationships separately',
    ):
        assert phrase in text
    for mode in ('Independent recovery', 'Notes-assisted recovery', 'Results-derived definitions'):
        assert mode in text


def test_civd_example_is_edition_pinned_and_attributed():
    text = read_reference(REFERENCE)
    links = re.findall(r'\]\((https://github\.com/sjmelia/civd/[^)]+)\)', text)
    assert len(links) == 4
    assert all(CIVD_PIN in link for link in links)
    assert 'release/474.01' in text and '474.05' in text
    assert 'OpenCiv1' in text and 'attributed upstream reports' in text


@pytest.mark.parametrize('heading', [
    '## Collate guides into provisional Z blueprints',
    '### Weight agreement by lineage, not vote count',
    '### Draft Z early without pretending it is tested',
    '### Compare predictions with recovered behavior and observations',
])
def test_guide_blueprint_workflow_is_selectively_retrievable(heading):
    text = read_reference(REFERENCE)
    assert heading in text
    assert len(text.encode('utf-8')) < 65536


def test_entrypoint_and_classification_include_guide_derived_z():
    entry = ' '.join(read_reference('SKILL.md').split())
    text = ' '.join(read_reference(REFERENCE).split())
    assert 'provisional Z blueprints' in entry
    assert 'source lineage' in entry and 'retain outliers' in entry
    assert '| Guides, solutions, walkthroughs and analyses |' in text
    assert 'third-party behavioral reconstruction' in text
    assert 'not recovered source code' in text
    assert 'Do not wait for complete UDL recovery before drafting it' in text
    assert 'Keep this material out of an explicitly independent benchmark arm' in text


def test_guide_consensus_preserves_dependence_and_dissent():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'search priority, not truth or verification',
        'one source family for corroboration, not fourteen independent witnesses',
        'Unknown dependence stays unknown',
        'Record raw report counts separately from established source families',
        'Retain the dissenting claim and the cheapest discriminator',
        'source-bound finding can outweigh the majority',
        'neither is new independent corroboration',
    ):
        assert phrase in text


def test_draft_z_keeps_hypotheses_and_execution_authority_separate():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'explicitly untested prediction artifact',
        'Illustrative PQ1-style hypothesis, not a factual claim',
        'code identity, visibility and availability unknown',
        'Failure of one string search does not establish absence',
        'qualify any live click geometry separately',
        'Do not drive a live guest or mutate authoritative game state',
        'Future/hidden objects stay in the investigator',
    ):
        assert phrase in text


def test_z_comparison_keeps_original_predictions_and_scoped_results():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'Keep the pre-analysis draft revision',
        'guide-derived Z prediction, source-qualified UDL/UIL behavior, and original-runtime observation',
        'A missing observation is unknown, not a contradiction',
        'supported at a stated boundary, refined, contradicted or still unresolved',
        'comparison point, not the sole oracle',
        'internal consistency only',
        'coverage of its claims, not the whole game',
        'correction/preparation cost',
    ):
        assert phrase in text


@pytest.mark.parametrize('heading', [
    '## Initial documentation pass after target triage',
    '### Case study seed: an English FF7 guide and regional clock instructions',
])
def test_initial_documentation_and_transfer_case_are_retrievable(heading):
    text = read_reference(REFERENCE)
    assert heading in text
    assert len(text.encode('utf-8')) < 65536


def test_documentation_follows_triage_before_expensive_recovery():
    entry = ' '.join(read_reference('SKILL.md').split())
    text = ' '.join(read_reference(REFERENCE).split())
    assert ('initial target analysis -> initial documentation pass -> provisional '
            'blueprints and hypotheses -> focused code/runtime verification') in entry
    assert 'Do not wait for complete disassembly, an exact build number' in text
    assert 'normal first-phase deliverable, not an optional rescue' in text


def test_related_versions_are_hypothesis_inputs_not_automatic_bindings():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'Exact matching is a preference, not an admission prerequisite',
        'versions, platforms, localizations, ports or engine families',
        'does not transfer qualified addresses, object IDs, binary layouts, timing or input sequences automatically',
        'applicability per claim, not as a single trusted/untrusted guide flag',
    ):
        assert phrase in text


def test_document_language_and_game_edition_remain_distinct():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        "Record the document's language separately from the game edition/region",
        'an English guide need not describe the US game',
        'translated aliases without treating lexical matches as object identity',
        'translated/reposted guide retains its upstream lineage',
    ):
        assert phrase in text


def test_ff7_recollection_is_not_promoted_to_verified_history():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'TiGa reports remembering',
        'not independently verified publication history',
        'guide title, publisher, printing/page and compared game releases',
        'not evidence of the guide\'s Japanese provenance or a complete JP/US comparison',
        'no guide-page comparison was completed',
    ):
        assert phrase in text


def test_local_mismatch_preserves_unrelated_leads_without_certifying_them():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'without deleting unrelated leads',
        'a clock mismatch neither disproves nor validates them',
        'version-qualified alternatives for the clock procedure',
        'not a reason to throw away the rest of the guide or declare the rest correct',
    ):
        assert phrase in text


def test_documentation_is_bounded_and_preserves_blind_exceptions():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'Stop gathering when the next useful probe is defined',
        'absence of documentation must not block all analysis',
        'retrieval, translation, collation and correction costs',
        'not a guaranteed speedup',
        'a user-requested blind/independent recovery arm',
        'Record the reason when the documentation pass is omitted',
        'State what would contradict it',
    ):
        assert phrase in text
