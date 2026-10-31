"""Authored package-binding fixtures, never original KQ1 bytes or messages.

The internal edition profile is monkeypatched for positive mapping-mechanics
tests and explicitly marked unqualified. These fixtures do not establish any
original-game semantic or native execution claim.
"""
from copy import deepcopy
import gzip
from hashlib import sha256
import json

import pytest

from fdisbull import kq1_bow
from fdisbull.agi_resources import V2Resources
from fdisbull.agi_scenes import inspect_scenes
from fdisbull.court_intents import canonical_digest


def _logic(code, messages):
    offsets, strings = [], b''
    for message in messages:
        if message is None:
            offsets.append(0)
        else:
            offsets.append(2 + 2 * len(messages) + len(strings))
            strings += message.encode('ascii') + b'\0'
    encrypted = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(strings))
    return (len(code).to_bytes(2, 'little') + code + bytes([len(messages)])
            + (2 + 2 * len(messages) + len(strings)).to_bytes(2, 'little')
            + b''.join(offset.to_bytes(2, 'little') for offset in offsets) + encrypted)


@pytest.fixture
def authored_game(tmp_path):
    game = tmp_path / 'authored-game'
    game.mkdir()
    messages = [None] * 55
    for name, number in kq1_bow.MESSAGE_BINDINGS.items():
        messages[number - 1] = 'Authored fixture ' + name
    # A byte-aligned array of returns only exercises witness framing. It does
    # not imitate the original game algorithm or qualify the semantic mapping.
    payload = _logic(b'\0' * (0x48d - 2), messages)
    helper = _logic(b'\x01\x03\0', [])  # authored increment(v3); return
    volume = bytearray()
    directory = bytearray(b'\xff\xff\xff' * 54)
    for number, body in ((0, helper), (53, payload)):
        directory[number * 3:number * 3 + 3] = len(volume).to_bytes(3, 'big')
        volume += b'\x12\x34\0' + len(body).to_bytes(2, 'little') + body
    (game / 'LOGDIR').write_bytes(directory)
    (game / 'VOL.0').write_bytes(volume)
    for filename in ('PICDIR', 'VIEWDIR', 'SNDDIR'):
        (game / filename).write_bytes(b'')
    return game


@pytest.fixture
def authored_profile(authored_game, monkeypatch):
    resources = V2Resources(authored_game)
    logic = next(row for row in resources.resources('logic') if row['number'] == 53)
    census = inspect_scenes(authored_game, profile='2.917', include_ir=True, include_text=True)
    profile = {
        'id': 'authored-test-fixture-not-kq1',
        'qualification': 'unqualified_authored_mapping_fixture',
        'logic_source': {key: value for key, value in logic.items() if key != 'payload'},
        'manifest_sha256': canonical_digest(resources.manifest()),
        'census_sha256': canonical_digest(census),
    }
    monkeypatch.setattr(kq1_bow, '_EDITION', profile)
    return authored_game, census


@pytest.fixture
def authored_package(authored_profile):
    game, _ = authored_profile
    return kq1_bow.recover_bow(game)


def test_unqualified_resource_set_is_rejected(authored_game):
    with pytest.raises(ValueError, match='Exact qualified KQ1 resource set'):
        kq1_bow.recover_bow(authored_game)


def test_authored_package_preserves_all_census_and_names_only_separate_intent(authored_profile):
    game, census = authored_profile
    package = kq1_bow.recover_bow(game)
    assert package['low_level_ir'] == census
    assert [row['logic'] for row in package['low_level_ir']['logics']] == [0, 53]
    assert all(row['representation'] == 'low_level_ir' for row in census['logics'])
    assert census['coverage']['accepted_uil_interactions'] == 0
    assert census['coverage']['scene_discovery_complete'] is False
    assert package['uil']['resources']['response'] == 'Authored fixture response'
    receipt = kq1_bow.verify_bow_package(package)
    assert receipt['edition_qualification'] == 'unqualified_authored_mapping_fixture'
    assert receipt['native_execution_verified'] is False
    assert receipt['all_game_intent_recovered'] is False
    assert receipt['witness_count'] == 18


@pytest.mark.parametrize('binding', ['respect_awarded', 'input_consumed', 'score', 'actor_x'])
def test_recomputed_digests_cannot_authorize_remapped_fields(authored_package, binding):
    row = authored_package['udl']['field_bindings'][binding]
    row['number'] += 1
    authored_package['udl']['uil_sha256'] = canonical_digest(authored_package['uil'])
    with pytest.raises(ValueError, match='UDL source mapping or qualification'):
        kq1_bow.verify_bow_package(authored_package)


@pytest.mark.parametrize('which', ['flag15', 'timer21', 'room', 'entry', 'geometry',
                                  'engine_order', 'clock_fields'])
def test_exact_qualification_and_engine_bindings_are_not_package_authority(authored_package, which):
    udl = authored_package['udl']
    if which == 'flag15':
        udl['qualification']['flags_equal']['15'] = True
    elif which == 'timer21':
        udl['qualification']['variables_equal']['21'] = 1
    elif which == 'room':
        udl['qualification']['variables_equal']['0'] = 54
    elif which == 'entry':
        udl['source_entry'] += 1
    elif which == 'geometry':
        udl['geometry_bindings']['addressing']['rectangle'][0] += 1
    elif which == 'clock_fields':
        # Advancing host clock fields must never authorize a score mutation.
        udl['qualification']['modal_host_mutable_variables'].append(3)
        udl['uil_sha256'] = canonical_digest(authored_package['uil'])
        udl['low_level_ir_sha256'] = canonical_digest(authored_package['low_level_ir'])
    else:
        requests = udl['engine_requests']['court.finish_bow']
        requests[1], requests[2] = requests[2], requests[1]
    with pytest.raises(ValueError, match='UDL source mapping or qualification'):
        kq1_bow.verify_bow_package(authored_package)


def test_boolean_qualification_cannot_be_replaced_by_equal_integer(authored_package):
    authored_package['udl']['qualification']['flags_equal']['15'] = 0
    with pytest.raises(ValueError, match='UDL source mapping or qualification'):
        kq1_bow.verify_bow_package(authored_package)


def test_model_digest_recalculation_does_not_authorize_changed_intent(authored_package):
    authored_package['uil']['reward']['points'] = 4
    authored_package['udl']['uil_sha256'] = canonical_digest(authored_package['uil'])
    with pytest.raises(ValueError, match='UIL source-derived definition'):
        kq1_bow.verify_bow_package(authored_package)


def test_uil_text_is_checked_against_original_message_table(authored_package):
    authored_package['uil']['resources']['response'] = 'Invented different result'
    authored_package['udl']['uil_sha256'] = canonical_digest(authored_package['uil'])
    with pytest.raises(ValueError, match='UIL source-derived definition'):
        kq1_bow.verify_bow_package(authored_package)


def test_message_number_remapping_is_rejected(authored_package):
    authored_package['udl']['resource_bindings']['response']['number'] = 7
    with pytest.raises(ValueError, match='UDL source mapping or qualification'):
        kq1_bow.verify_bow_package(authored_package)


def test_consistent_forged_witness_hash_does_not_match_source(authored_package):
    witness = authored_package['udl']['witnesses']['begin_bow']
    forged = b'X' * ((witness['end'] - witness['start']))
    witness['bytes'] = forged.hex()
    witness['sha256'] = sha256(forged).hexdigest()
    with pytest.raises(ValueError, match='UDL source mapping or qualification'):
        kq1_bow.verify_bow_package(authored_package)


def test_source_operation_tamper_is_rejected_even_with_rehashed_residual(authored_package):
    census = authored_package['low_level_ir']
    row = next(row for row in census['logics'] if row['logic'] == 0)
    row['ir']['instructions'][0]['operands'] = [99]
    row['ir']['sha256'] = canonical_digest(row['ir']['instructions'])
    census['sha256'] = canonical_digest({key: value for key, value in census.items() if key != 'sha256'})
    authored_package['udl']['low_level_ir_sha256'] = canonical_digest(census)
    with pytest.raises(ValueError, match='Complete retained census identity changed'):
        kq1_bow.verify_bow_package(authored_package)


def test_recomputed_payload_hash_does_not_qualify_different_source(authored_package):
    source = authored_package['source_logic']
    raw = bytearray.fromhex(source['payload'])
    raw[2] = 1
    source['payload'] = raw.hex()
    source['sha256'] = sha256(raw).hexdigest()
    authored_package['udl']['source_logic_sha256'] = source['sha256']
    with pytest.raises(ValueError, match='Exact qualified LOGIC53 payload identity'):
        kq1_bow.verify_bow_package(authored_package)


def test_independent_read_snapshots_must_agree(authored_profile, monkeypatch):
    game, census = authored_profile
    changed = deepcopy(census)
    changed['source']['volumes'][0]['sha256'] = '0' * 64
    monkeypatch.setattr(kq1_bow, 'inspect_scenes', lambda *args, **kwargs: changed)
    with pytest.raises(ValueError, match='Resource snapshot identity'):
        kq1_bow.recover_bow(game)


def test_export_exact_views_and_gzip_roundtrip(authored_profile, tmp_path):
    game, _ = authored_profile
    package_path = tmp_path / 'private' / 'bow.json.gz'
    uil_path, udl_path = tmp_path / 'private' / 'uil.json', tmp_path / 'private' / 'udl.json'
    receipt = kq1_bow.export_bow(game, output=package_path, uil=uil_path, udl=udl_path)
    with gzip.open(package_path, 'rt') as stream:
        package = json.load(stream)
    assert json.loads(uil_path.read_text()) == package['uil']
    assert json.loads(udl_path.read_text()) == package['udl']
    assert receipt['bindings'] == kq1_bow.verify_bow_package(package)
    with pytest.raises(FileExistsError):
        kq1_bow.export_bow(game, output=package_path)


def test_export_preflights_every_destination(authored_profile, tmp_path):
    game, _ = authored_profile
    output = tmp_path / 'output.json'
    occupied = tmp_path / 'occupied.json'
    occupied.write_text('existing authored file')
    with pytest.raises(FileExistsError):
        kq1_bow.export_bow(game, output=output, udl=occupied)
    assert not output.exists()
    assert occupied.read_text() == 'existing authored file'
    with pytest.raises(ValueError, match='distinct'):
        kq1_bow.export_bow(game, output=output, uil=output)
    with pytest.raises(ValueError, match='separate from original game inputs'):
        kq1_bow.export_bow(game, output=game / 'generated.json')


def test_export_refuses_game_derived_material_inside_git(authored_profile, tmp_path):
    game, _ = authored_profile
    checkout = tmp_path / 'checkout'
    (checkout / '.git').mkdir(parents=True)
    (checkout / '.git' / 'HEAD').write_text('ref: refs/heads/authored\n')
    with pytest.raises(ValueError, match='outside a Git checkout'):
        kq1_bow.export_bow(game, output=checkout / 'bow.json')
    assert not (checkout / 'bow.json').exists()
