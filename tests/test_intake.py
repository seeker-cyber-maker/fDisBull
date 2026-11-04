"""Single and batch intake must share evidence and leave authored inputs intact."""
import hashlib
import os
from pathlib import Path
import struct

import pytest

from fdisbull.intake import intake_inventory


def wave():
    return b'RIFF' + struct.pack('<I', 4) + b'WAVE'


def _file(root, name, data):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_single_and_batch_use_same_kernel_and_preserve_originals(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    one = _file(a, 'SOUND.DAT', wave())
    two = _file(b, 'manual.txt', b'Authored ordinary text.\n')
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (one, two)}
    solo = intake_inventory(a)
    batch = intake_inventory([a, b])
    assert solo['complete'] and batch['complete']
    single = solo['files'][0]
    assert single == batch['files'][0]
    assert single['identification']['format_id'] == 'riff-wave'
    assert single['source']['hash_scope'] == 'whole opened file'
    assert batch['roots'][1]['files_reported'] == 1
    assert not batch['input_executed'] and not batch['executables_modified']
    assert not batch['full_media_decode'] and not batch['native_runtime_tested']
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


def test_unknown_suffixes_are_hints_and_recovery_groups_are_deduplicated(tmp_path):
    _file(tmp_path, 'a.mystery', b'First authored unknown resource')
    _file(tmp_path, 'b.mystery', b'Second authored unknown resource')
    _file(tmp_path, 'README.txt', b'ordinary documentation, not evidence of a movie')
    result = intake_inventory(tmp_path)
    assert result['complete'] and len(result['files']) == 3
    groups = [g for g in result['recovery_queue'] if g['extension_hint'] == '.mystery']
    assert len(groups) == 1 and groups[0]['count'] == 2
    assert groups[0]['reason'] == 'unknown-format' and groups[0]['format_id'] is None
    assert all(row['identification']['format_id'] is None for row in result['files'])
    assert not any(g['reason'] == 'media-decoder-recovery' for g in result['recovery_queue'])


def test_known_media_header_does_not_claim_decoding(tmp_path):
    _file(tmp_path, 'SOUND.WAV', wave())
    report = intake_inventory(tmp_path)
    row = report['files'][0]
    assert row['identification']['category'] == 'audio'
    assert row['identification']['full_decode'] is False
    assert any(g['reason'] in ('media-decoder-recovery', 'media-validation-needed') for g in report['recovery_queue'])
    assert row['identification']['decoder_modules']
    assert report['decoder_modules']


@pytest.mark.parametrize('kind', ['mz', 'nes'])
def test_code_wrappers_leave_embedded_media_explicitly_unqualified(tmp_path, kind):
    if kind == 'mz':
        data = struct.pack('<14H', 0x5a4d, 36, 1, 0, 2, 0, 0, 0, 0, 0, 0, 0, 28, 0) + bytes(4) + b'CODE'
    else:
        data = b'NES\x1a' + bytes([1, 0]) + bytes(10) + bytes(16384)
    report = intake_inventory(_file(tmp_path, 'program', data))
    assert report['complete']
    assert report['files'][0]['identification']['category'] in ('executable', 'console-media')
    groups = [group for group in report['recovery_queue'] if group['reason'] == 'embedded-media-unqualified']
    assert len(groups) == 1
    assert report['full_media_decode'] is False


def test_context_candidates_preserve_companion_recovery_without_becoming_headers(tmp_path):
    root = tmp_path / 'dinopark-authored'
    _file(root, 'AUTHORED.ABT', b'Unknown authored actor table, not an executable header')
    report = intake_inventory(root)
    row = report['files'][0]
    assert row['identification']['format_id'] is None
    candidates = [hint for hint in row['candidate_profiles'] if hint['format_id'] == 'context-dinopark-abt']
    assert candidates and candidates[0]['qualification'] == 'context-candidate-only'
    assert isinstance(candidates[0]['companions'], list) and candidates[0]['recovery']
    assert report['recovery_queue'][0]['candidate_profiles'] == row['candidate_profiles']


def test_authored_context_profile_carries_companions_without_decoding_or_loading_plugins(tmp_path):
    import json
    import sqlite3
    from fdisbull.format_registry import format_catalog
    root = tmp_path / 'authored-game'
    _file(root, 'sample.WHATEVER', b'An unknown authored resource')
    catalog = tmp_path / 'formats.sqlite'
    format_catalog(catalog_path=catalog)
    row = dict(format_id='authored-context', revision=1, name='Authored resource family',
        category='animation-container', signatures=[], header_fields=[], detection='consumer-context-only',
        context_hints=dict(filename_patterns=['*.WHATEVER'], game_markers=['authored-game'],
                           companions=['TABLE.IDX', 'PALETTE.PAL']),
        limitations=['Recover authored packet extents and palette ownership.'])
    with sqlite3.connect(catalog) as db:
        db.execute('INSERT INTO format_definitions VALUES (?,?,?)', ('authored-context', 1, json.dumps(row)))
    result = intake_inventory(root, catalog_path=catalog)
    assert result['complete'] and result['catalog']['contains_file_payloads'] is None
    identified = result['files'][0]
    assert identified['identification']['format_id'] is None
    hint = next(h for h in identified['candidate_profiles'] if h['format_id'] == 'authored-context')
    assert hint['qualification'] == 'context-candidate-only'
    assert hint['companions'] == ['TABLE.IDX', 'PALETTE.PAL']
    assert hint['recovery'] == row['limitations']


def test_invalid_header_is_a_variant_recovery_not_io_failure(tmp_path):
    _file(tmp_path, 'broken.smk', b'SMK2')
    report = intake_inventory(tmp_path)
    assert report['complete'] and not report['errors']
    assert report['files'][0]['identification']['status'] == 'recognized-invalid'
    assert report['recovery_queue'][0]['reason'] == 'invalid-header-or-variant'


def test_directory_symlink_cycle_is_not_followed_and_gap_is_explicit(tmp_path):
    _file(tmp_path, 'source.dat', wave())
    (tmp_path / 'loop').symlink_to('.', target_is_directory=True)
    result = intake_inventory(tmp_path)
    assert not result['complete'] and len(result['files']) == 1
    assert result['skipped'][0]['reason'] == 'directory-symlink-not-followed'
    assert result['skipped'][0]['member'] == 'loop'


def test_regular_file_symlinks_preserve_requested_and_resolved_identity(tmp_path):
    source = _file(tmp_path, 'source', wave())
    alias = tmp_path / 'alias.wav'
    alias.symlink_to(source)
    result = intake_inventory(alias)
    row = result['files'][0]
    assert result['complete'] and row['is_symlink']
    assert row['path'] == str(alias) and row['resolved_path'] == str(source)
    assert row['source']['sha256'] == hashlib.sha256(wave()).hexdigest()


def test_missing_source_is_io_failure_without_fabricated_format(tmp_path):
    missing = tmp_path / 'missing'
    present = _file(tmp_path, 'present', wave())
    report = intake_inventory([missing, present])
    assert not report['complete']
    assert report['errors'][0]['kind'] == 'io-error'
    assert len(report['files']) == 1 and report['files'][0]['root_index'] == 1
    assert report['roots'][1]['complete']


def test_file_budget_stops_before_reading_remaining_members(tmp_path):
    _file(tmp_path, 'a.wav', wave())
    _file(tmp_path, 'b.wav', wave())
    report = intake_inventory(tmp_path, max_files=1)
    assert not report['complete'] and len(report['files']) == 1
    assert report['files'][0]['member'] == 'a.wav'
    assert report['budgets']['stop_reason'] == 'max-files'


def test_read_budget_is_enforced_before_source_reads(tmp_path):
    source = _file(tmp_path, 'source.wav', wave())
    report = intake_inventory(source, max_read_bytes=4)
    assert not report['complete']
    assert report['budgets']['bytes_read'] <= 4
    assert report['budgets']['stop_reason'] == 'max-read-bytes'
    assert report['files'][0]['status'] == 'read-budget-not-inspected'
    assert not report['recovery_queue']


def test_catalog_must_be_outside_inputs_and_contains_no_source_payload(tmp_path):
    root = tmp_path / 'game'
    _file(root, 'unknown', b'PRIVATE_AUTHORED_SENTINEL')
    with pytest.raises(ValueError, match='outside'):
        intake_inventory(root, catalog_path=root / 'formats.sqlite')
    assert not (root / 'formats.sqlite').exists()
    catalog = tmp_path / 'formats.sqlite'
    report = intake_inventory(root, catalog_path=catalog)
    assert report['complete'] and catalog.is_file()
    assert b'PRIVATE_AUTHORED_SENTINEL' not in catalog.read_bytes()
    assert not report['inspected_source_bytes_persisted']


def test_hardlinked_catalog_is_refused_before_seeding_or_source_reads(tmp_path):
    from fdisbull.format_registry import format_catalog
    root = tmp_path / 'game'
    root.mkdir()
    catalog = tmp_path / 'formats.sqlite'
    format_catalog(catalog_path=catalog)
    alias = root / 'catalog-alias'
    os.link(catalog, alias)
    before = catalog.read_bytes()
    with pytest.raises(ValueError, match='aliases the catalog'):
        intake_inventory(root, catalog_path=catalog)
    assert catalog.read_bytes() == alias.read_bytes() == before


def test_symlink_member_to_external_catalog_refuses_before_any_reseeding(tmp_path):
    import sqlite3
    from fdisbull.format_registry import format_catalog
    root = tmp_path / 'game'
    root.mkdir()
    catalog = tmp_path / 'formats.sqlite'
    format_catalog(catalog_path=catalog)
    # Removing one shipped record would ordinarily be repaired during seeding.
    with sqlite3.connect(catalog) as db:
        db.execute('DELETE FROM format_decoder_links WHERE format_id=?', ('smacker',))
        db.execute('DELETE FROM format_definitions WHERE format_id=?', ('smacker',))
    (root / 'catalog-alias.dat').symlink_to(catalog)
    before = catalog.read_bytes()
    with pytest.raises(ValueError, match='aliases the catalog'):
        intake_inventory(root, catalog_path=catalog)
    assert catalog.read_bytes() == before


@pytest.mark.parametrize('existing', [False, True])
def test_incomplete_enumeration_never_creates_or_modifies_requested_catalog(tmp_path, existing):
    from fdisbull.format_registry import format_catalog
    root = tmp_path / 'game'
    _file(root, 'a.wav', wave())
    _file(root, 'b.wav', wave())
    catalog = tmp_path / 'formats.sqlite'
    if existing:
        format_catalog(catalog_path=catalog)
    before = catalog.read_bytes() if existing else None
    result = intake_inventory(root, catalog_path=catalog, max_files=1)
    assert not result['complete']
    assert result['catalog']['path'] is None
    assert result['catalog']['requested_path'] == str(catalog)
    assert result['catalog']['persistence'] == 'not-written-incomplete-enumeration'
    if existing:
        assert catalog.read_bytes() == before
    else:
        assert not catalog.exists()
    assert result['files'][0]['identification']['format_id'] == 'riff-wave'


def test_reader_refusal_is_flagged_for_recovery_separately_from_io(tmp_path, monkeypatch):
    from fdisbull import format_registry
    source = _file(tmp_path, 'source.dat', wave())
    def refuse(*args, **options):
        error = ValueError('Unsupported authored profile')
        error.bytes_read = 0
        error.sampled_regions = []
        raise error
    monkeypatch.setattr(format_registry, '_identify_file_with_catalog', refuse)
    report = intake_inventory(source)
    assert not report['complete']
    assert report['errors'][0]['kind'] == 'reader-refusal'
    assert report['recovery_queue'][0]['reason'] == 'reader-refusal'


def test_opened_identity_detects_a_source_changed_after_enumeration(tmp_path, monkeypatch):
    from fdisbull import format_registry
    source = _file(tmp_path, 'source.wav', wave())
    original = format_registry._identify_file_with_catalog
    def changed(path, *args, **options):
        Path(path).write_bytes(b'UNKNOWN_AUTHORED_REPLACEMENT')
        return original(path, *args, **options)
    monkeypatch.setattr(format_registry, '_identify_file_with_catalog', changed)
    report = intake_inventory(source)
    assert not report['complete']
    assert report['files'][0]['status'] == 'source-changed'
    assert report['errors'][0]['kind'] == 'source-changed'
    assert not report['recovery_queue']


def test_file_link_retargeting_cannot_misbind_identification(tmp_path, monkeypatch):
    from fdisbull import format_registry
    source = _file(tmp_path, 'source.wav', wave())
    other = _file(tmp_path, 'other.wav', wave())
    alias = tmp_path / 'alias.wav'
    alias.symlink_to(source)
    original = format_registry._identify_file_with_catalog
    def changed(path, *args, **options):
        alias.unlink()
        alias.symlink_to(other)
        return original(path, *args, **options)
    monkeypatch.setattr(format_registry, '_identify_file_with_catalog', changed)
    report = intake_inventory(alias)
    assert not report['complete'] and report['files'][0]['status'] == 'source-changed'
    assert report['errors'][0]['kind'] == 'source-changed'


def test_recursive_enumeration_has_a_separate_entry_budget(tmp_path):
    # Empty directory fanout cannot bypass max_files simply by containing no files.
    for i in range(10):
        (tmp_path / f'd{i}').mkdir()
    result = intake_inventory(tmp_path, max_files=1)
    assert not result['complete'] and not result['files']
    assert result['budgets']['stop_reason'] == 'max-filesystem-entries'
    assert result['budgets']['filesystem_entries_discovered'] <= result['budgets']['max_filesystem_entries']


def test_special_file_is_not_opened(tmp_path):
    fifo = tmp_path / 'pipe'
    os.mkfifo(fifo)
    report = intake_inventory(fifo)
    assert not report['complete'] and not report['files']
    assert report['skipped'][0]['reason'] == 'non-regular-file-not-read'
    assert report['budgets']['bytes_read'] == 0


@pytest.mark.parametrize('option', ['max_files', 'max_read_bytes', 'max_binary_bytes'])
@pytest.mark.parametrize('bad', [0, True, -1])
def test_invalid_budgets_refuse_before_catalog_creation(tmp_path, option, bad):
    catalog = tmp_path / 'new.sqlite'
    with pytest.raises(ValueError):
        intake_inventory(tmp_path, catalog_path=catalog, **{option: bad})
    assert not catalog.exists()
