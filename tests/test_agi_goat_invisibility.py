"""Authored source-layout and solver checks, without original game fixtures."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from examples.agi import check_goat_invisibility as check


def authored_resource(code, number=5):
    code = bytes(code)
    return SimpleNamespace(
        logic=number, code=code, payload=len(code).to_bytes(2, 'little') + code,
        space=f'authored.logic.{number}', profile='2.917', resource_sha256=sha256(code).hexdigest(),
        directory_sha256='authored-directory', volume=0, volume_sha256='authored-volume',
    )


def test_writer_scan_uses_boundaries_and_retains_all_dynamic_writers():
    # The operand 12 in assignn must never become a false set-flag instruction.
    first = authored_resource([3, 12, 75, 12, 75, 13, 79, 15, 7, 16, 9, 17, 10, 0])
    second = authored_resource([14, 79, 12, 8, 0], number=9)
    assert check.writers({9: second, 5: first}) == [
        dict(logic=5, offset=3, opcode=12, operand=75),
        dict(logic=5, offset=5, opcode=13, operand=79),
        dict(logic=5, offset=7, opcode=15, operand=7),
        dict(logic=5, offset=9, opcode=16, operand=9),
        dict(logic=5, offset=11, opcode=17, operand=10),
        dict(logic=9, offset=0, opcode=14, operand=79),
    ]


def test_truncated_dynamic_writer_refuses_instead_of_skipping_unknown_effect():
    with pytest.raises(ValueError, match='Truncated'):
        check.writers({5: authored_resource([15])})


def test_unexpected_action_refuses_instead_of_claiming_writer_scan_complete():
    with pytest.raises(ValueError, match='Unsupported AGI v2.917 action'):
        check.writers({5: authored_resource([174])})


def test_source_loader_scans_every_present_directory_entry(tmp_path):
    volume = bytearray()
    entries = []
    for code in ([12, 75, 0], None, [13, 79, 0]):
        if code is None:
            entries.append(b'\xff\xff\xff')
            continue
        payload = len(code).to_bytes(2, 'little') + bytes(code)
        entries.append(len(volume).to_bytes(3, 'big'))
        volume.extend(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    (tmp_path / 'LOGDIR').write_bytes(b''.join(entries))
    (tmp_path / 'VOL.0').write_bytes(volume)
    resources = check.load_resources(tmp_path / 'LOGDIR', tmp_path, '2.917')
    assert set(resources) == {0, 2}
    assert [(row['logic'], row['opcode'], row['operand']) for row in check.writers(resources)] == [
        (0, 12, 75), (2, 13, 79),
    ]
    with pytest.raises(ValueError, match='Unqualified exact-edition LOGDIR'):
        check.qualify_source(resources)


@pytest.mark.parametrize('profile', ['2.915', '3.002', '', None])
def test_unexpected_profile_refuses_before_source_access(tmp_path, profile):
    with pytest.raises(ValueError, match='explicit 2.917'):
        check.load_resources(tmp_path / 'absent', tmp_path, profile)


def test_unexpected_writer_inventory_is_not_assumed_away():
    resources = {}
    for number in (0, 10, 11, 99, 103):
        resource = authored_resource([12, 79, 0], number)
        resource.directory_sha256 = check.DIRECTORY_SHA256
        resource.volume_sha256 = check.VOLUME_SHA256[0]
        resources[number] = resource
    with pytest.raises(ValueError, match='Unexpected literal or dynamic flag writers'):
        check.qualify_source(resources)


def test_volume_identity_mismatch_refuses_before_guard_or_solver():
    resource = authored_resource([0])
    resource.directory_sha256 = check.DIRECTORY_SHA256
    with pytest.raises(ValueError, match='Unqualified exact-edition volume'):
        check.qualify_source({5: resource})


def authored_guard():
    # IF !following && !invisible: set following; return; ELSE return.
    # This is authored from the AGI encoding contract, not a game resource.
    code = bytes([255, 253, 7, 75, 253, 7, 79, 255, 3, 0, 12, 75, 0, 0])
    return code, sha256(code[:10]).hexdigest()


def test_decoded_guard_edge_must_dominate_literal_writer():
    code, witness = authored_guard()
    result = check.qualify_guard(authored_resource(code), 0, 10,
                                 ((75, False), (79, False)), witness)
    assert result['edge_dominates_target']
    assert result['terms'] == [dict(flag=75, required=False), dict(flag=79, required=False)]


def test_an_additional_path_into_writer_invalidates_guard_witness():
    code, witness = authored_guard()
    # An independent entry condition can jump directly into the body, bypassing
    # the otherwise valid conjunction at offset 9.
    prefix = bytes([255, 7, 1, 255, 3, 0, 254, 10, 0])
    resource = authored_resource(prefix + code)
    with pytest.raises(ValueError, match='does not dominate'):
        check.qualify_guard(resource, 9, 19, ((75, False), (79, False)), witness)


def test_hash_match_does_not_replace_decoded_guard_check():
    code, witness = authored_guard()
    with pytest.raises(ValueError, match='Decoded guard differs'):
        check.qualify_guard(authored_resource(code), 0, 10, ((75, True), (79, False)), witness)


def test_modified_guard_bytes_refuse_before_dominance_claim():
    code, witness = authored_guard()
    changed = bytearray(code)
    changed[6] = 78
    with pytest.raises(ValueError, match='Guard byte witness differs'):
        check.qualify_guard(authored_resource(changed), 0, 10,
                            ((75, False), (79, False)), witness)


def test_disjunction_is_not_silently_interpreted_as_conjunction():
    with pytest.raises(ValueError, match='conjunction'):
        check.flag_terms([{'marker': 'or'}, {'opcode': 7, 'operands': [75]}])


@pytest.mark.parametrize('steps', [2, 8])
def test_z3_induction_and_bounded_query_with_debug_negative_control(steps):
    pytest.importorskip('z3')
    result = check.solve_flags(steps)
    assert result['initial_violation'] == 'unsat'
    assert result['inductive_step_violation'] == 'unsat'
    assert result['bounded_violation'] == 'unsat'
    assert result['debug_negative_control'] == 'sat'
    assert result['negative_control_witness'] == [
        dict(following=False, invisible=False),
        dict(following=True, invisible=False),
        dict(following=True, invisible=True),
    ]
    assert result['verified']


@pytest.mark.parametrize('steps', [True, 1, 65, 2.0])
def test_solver_bound_is_explicit_and_fail_closed(steps):
    pytest.importorskip('z3')
    with pytest.raises(ValueError, match='steps must be 2..64'):
        check.solve_flags(steps)
