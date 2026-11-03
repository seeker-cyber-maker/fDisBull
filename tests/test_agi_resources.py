"""Authored resource containers; no original Sierra data is distributed."""
from hashlib import sha256
from pathlib import Path

import pytest

from fdisbull.agi_resources import V2Resources, logic_messages


def _resource(payload, volume=0):
    return b'\x12\x34' + bytes([volume]) + len(payload).to_bytes(2, 'little') + payload


def _entry(volume, offset):
    return ((volume << 20) | offset).to_bytes(3, 'big')


def _containers(root):
    """Two logics, one aliasing picture and an absent directory slot."""
    a = _resource(b'\x01\x00\x00\x00\x02\x00')
    b = _resource(b'picture')
    (root / 'VOL.0').write_bytes(a + b)
    (root / 'LOGDIR').write_bytes(_entry(0, 0) + b'\xff\xff\xff' + _entry(0, 0))
    (root / 'PICDIR').write_bytes(_entry(0, len(a)))
    (root / 'VIEWDIR').write_bytes(b'')
    return a, b


def test_census_identity_aliases_and_cached_reads(tmp_path, monkeypatch):
    first, second = _containers(tmp_path)
    calls = []
    original = Path.open

    def counted(path, *args, **kwargs):
        if path.parent == tmp_path:
            calls.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', counted)
    store = V2Resources(tmp_path)
    rows = store.resources('logic')
    assert [r['number'] for r in rows] == [0, 2]
    assert all(r['status'] == 'ok' and r['payload'] == first[5:] for r in rows)
    picture = store.resources('picture')[0]
    assert picture['offset'] == len(first) and picture['payload'] == b'picture'
    assert picture['sha256'] == sha256(b'picture').hexdigest()
    assert store.resources('view') == store.resources('sound') == []
    manifest = store.manifest()
    dirs = {d['kind']: d for d in manifest['directories']}
    assert dirs['logic']['entries'] == 3 and dirs['logic']['present'] == 2
    assert dirs['sound']['status'] == 'absent'
    assert dirs['view']['status'] == 'ok' and dirs['view']['entries'] == 0
    assert manifest['volumes'][0]['sha256'] == sha256(first + second).hexdigest()
    assert manifest['read_counts'] == {'LOGDIR': 1, 'PICDIR': 1, 'VIEWDIR': 1, 'VOL.0': 1}
    assert sorted(calls) == ['LOGDIR', 'PICDIR', 'VIEWDIR', 'VOL.0']
    assert str(tmp_path) not in str(manifest)
    rows[0]['payload'] = b'caller mutation'
    manifest['directories'].clear()
    assert store.resources('logic')[0]['payload'] == first[5:]
    assert len(store.manifest()['directories']) == 4
    assert sorted(calls) == ['LOGDIR', 'PICDIR', 'VIEWDIR', 'VOL.0']


def test_snapshot_does_not_mix_later_source_edits(tmp_path):
    _containers(tmp_path)
    store = V2Resources(tmp_path)
    before = store.resources('logic'), store.manifest()
    (tmp_path / 'VOL.0').write_bytes(b'changed')
    (tmp_path / 'LOGDIR').unlink()
    assert (store.resources('logic'), store.manifest()) == before


def test_case_insensitive_names_and_all_volume_bits(tmp_path):
    (tmp_path / 'loGDiR').write_bytes(_entry(15, 3))
    (tmp_path / 'VoL.15').write_bytes(b'pad' + _resource(b'test', volume=15))
    result = V2Resources(tmp_path)
    row = result.resources('logic')[0]
    assert row['volume'] == 15 and row['offset'] == 3 and row['payload'] == b'test'
    assert result.manifest()['read_counts'] == {'LOGDIR': 1, 'VOL.15': 1}


def test_absence_uses_offset_sentinel_not_volume_nibble(tmp_path):
    (tmp_path / 'LOGDIR').write_bytes(_entry(0, 0xfffff) + _entry(4, 0xfffff))
    store = V2Resources(tmp_path)
    assert store.resources('logic') == []
    assert store.manifest()['volumes'] == []
    assert store.manifest()['directories'][0]['present'] == 0


@pytest.mark.parametrize('name', ['LOGDIR', 'VOL.0'])
def test_ambiguous_case_is_explicit_error(tmp_path, name):
    _containers(tmp_path)
    other = tmp_path / name.lower()
    other.write_bytes((tmp_path / name).read_bytes())
    if other.samefile(tmp_path / name):
        pytest.skip('case-sensitive filesystem required')
    store = V2Resources(tmp_path)
    if name == 'LOGDIR':
        item = store.manifest()['directories'][0]
        assert store.resources('logic') == []
    else:
        item = store.resources('logic')[0]
    assert item['status'] == 'error' and 'ambiguous' in item['error'].lower()


@pytest.mark.parametrize('data', [b'x', b'\0' * 769])
def test_malformed_directory_preserves_other_kinds(tmp_path, data):
    _containers(tmp_path)
    (tmp_path / 'LOGDIR').write_bytes(data)
    store = V2Resources(tmp_path)
    assert store.manifest()['directories'][0]['status'] == 'error'
    assert store.resources('picture')[0]['status'] == 'ok'


@pytest.mark.parametrize('volume, reason', [
    (None, 'missing'),
    (b'\x12\x34', 'header'),
    (b'\x12\x35\x00\x00\x00', 'signature'),
    (_resource(b'a', volume=1), 'number'),
    (b'\x12\x34\x00\x02\x00a', 'truncated'),
    (b'x' * (2 * 1024 * 1024 + 1), 'limit'),
])
def test_bad_resources_are_recorded_individually(tmp_path, volume, reason):
    (tmp_path / 'LOGDIR').write_bytes(_entry(0, 0))
    (tmp_path / 'PICDIR').write_bytes(_entry(1, 0))
    (tmp_path / 'VOL.1').write_bytes(_resource(b'fine', volume=1))
    if volume is not None:
        (tmp_path / 'VOL.0').write_bytes(volume)
    store = V2Resources(tmp_path)
    bad = store.resources('logic')[0]
    assert bad['status'] == 'error' and reason in bad['error'].lower()
    assert 'payload' not in bad
    assert store.resources('picture')[0]['payload'] == b'fine'


def test_one_bad_entry_does_not_hide_valid_entry(tmp_path):
    (tmp_path / 'LOGDIR').write_bytes(_entry(0, 0) + _entry(0, 1000))
    (tmp_path / 'VOL.0').write_bytes(_resource(b'fine'))
    rows = V2Resources(tmp_path).resources('logic')
    assert [r['status'] for r in rows] == ['ok', 'error']


@pytest.mark.parametrize('kind', ['LOGDIR', 'room', None, 1])
def test_resource_kind_is_explicit(tmp_path, kind):
    with pytest.raises(ValueError, match='kind'):
        V2Resources(tmp_path).resources(kind)


def _logic(messages, *, offsets=None, code=b'\0'):
    """Authored writer: its public expected values are plain literal strings."""
    strings = b''
    table = []
    for msg in messages:
        if msg is None:
            table.append(0)
        else:
            table.append(2 + 2 * len(messages) + len(strings))
            strings += msg + b'\0'
    key = b'Avis Durgan'
    encrypted = bytes(c ^ key[i % len(key)] for i, c in enumerate(strings))
    table = table if offsets is None else offsets
    size = 2 + len(table) * 2 + len(strings)
    return (len(code).to_bytes(2, 'little') + code + bytes([len(table)])
            + size.to_bytes(2, 'little')
            + b''.join(n.to_bytes(2, 'little') for n in table) + encrypted)


def test_message_numbers_absence_literal_templates_and_cipher_continuity():
    payload = _logic([b'Longer than key', None, b'Second %v23', b'\x82'])
    rows = logic_messages(payload)
    assert [r['number'] for r in rows] == [1, 2, 3, 4]
    assert [r['text'] for r in rows] == ['Longer than key', None, 'Second %v23', 'é']
    assert rows[1]['offset'] is None
    assert rows[0]['offset'] == 14 and rows[2]['offset'] == 30
    assert rows[0]['text_sha256'] == sha256(b'Longer than key').hexdigest()
    assert rows[0]['length'] == len(b'Longer than key')


def test_independent_literal_cipher_vector():
    # "ABC\0D\0" XOR the first six bytes of "Avis Durgan" is
    # 00 34 2a 73 64 44. The second message starts at cipher index4.
    payload = bytes.fromhex('010000020c0006000a0000342a736444')
    assert [r['text'] for r in logic_messages(payload)] == ['ABC', 'D']


def test_message_pointer_aliases_and_suffixes_are_allowed():
    payload = _logic([b'Long word', None, None], offsets=[8, 8, 13])
    assert [r['text'] for r in logic_messages(payload)] == ['Long word', 'Long word', 'word']


def test_empty_message_table():
    assert logic_messages(bytes.fromhex('010000000200')) == []


@pytest.mark.parametrize('payload, reason', [
    (b'', 'length'),
    (b'\0' * 65536, 'length'),
    (bytes.fromhex('0000000200'), 'code'),
    (bytes.fromhex('0300000000'), 'section'),
    (bytes.fromhex('010000020200'), 'table'),
    (bytes.fromhex('010000000100'), 'size'),
    (bytes.fromhex('010000000300'), 'size'),
    (_logic([b'hello'], offsets=[3]), 'offset'),
    (_logic([b'hello'], offsets=[10]), 'offset'),
])
def test_message_framing_rejects_unsupported_data(payload, reason):
    with pytest.raises(ValueError, match=reason):
        logic_messages(payload)


def test_unterminated_message_is_not_silently_extended():
    payload = bytearray(_logic([b'hello']))
    payload[-1] ^= 1
    with pytest.raises(ValueError, match='terminated'):
        logic_messages(bytes(payload))


def test_trailing_unmodelled_message_bytes_are_explicitly_refused():
    with pytest.raises(ValueError, match='trailing'):
        logic_messages(_logic([b'hello']) + b'extra')


def _words(entries):
    """Author a WORDS.TOK file with alphabet indexes and prefix compression."""
    header = bytearray(52)
    records = bytearray()
    previous = ''
    for word, number in entries:
        prefix = 0
        while prefix < min(len(previous), len(word)) and previous[prefix] == word[prefix]:
            prefix += 1
        if 'a' <= word[0] <= 'z' and not any(header[(ord(word[0]) - 97) * 2:(ord(word[0]) - 97) * 2 + 2]):
            i = (ord(word[0]) - 97) * 2
            header[i:i + 2] = (52 + len(records)).to_bytes(2, 'big')
        records.append(prefix)
        suffix = bytearray(ord(c) ^ 0x7f for c in word[prefix:])
        suffix[-1] |= 0x80
        records.extend(suffix)
        records.extend(number.to_bytes(2, 'big'))
        previous = word
    return bytes(header + records + b'\0')


def _objects(entries):
    names = b''
    records = b''
    for name, room in entries:
        records += (3 * len(entries) + len(names)).to_bytes(2, 'little') + bytes([room])
        names += name + b'\0'
    plain = (3 * len(entries)).to_bytes(2, 'little') + b'\x10' + records + names
    return bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(plain))


def test_vocabulary_groups_keep_synonyms_special_roles_and_unindexed_words(tmp_path):
    words = _words([('ANYWORD', 1), ('a', 0), ('all', 9999), ('ask', 17),
                    ('request', 17), ('room', 23)])
    (tmp_path / 'WORDS.TOK').write_bytes(words)
    store = V2Resources(tmp_path)
    result = store.vocabulary()
    assert result['status'] == 'decoded'
    groups = {g['number']: g for g in result['groups']}
    assert groups[17] == {'number': 17, 'words': ['ask', 'request'], 'role': 'word_group'}
    assert groups[0]['role'] == 'ignored'
    assert groups[1]['role'] == 'any_word'
    assert groups[9999]['role'] == 'rest_of_input'
    assert result['entries'][0] == {'offset': 52, 'number': 1, 'word': 'ANYWORD', 'lookup_indexed': False}
    assert all(e['lookup_indexed'] for e in result['entries'][1:])
    assert result['source']['sha256'] == sha256(words).hexdigest()
    assert store.manifest()['read_counts'] == {'WORDS.TOK': 1}


def test_object_ids_names_and_initial_locations_are_literal(tmp_path):
    encrypted = _objects([(b'key', 0), (b'coin', 255), (b'\x82', 42)])
    (tmp_path / 'OBJECT').write_bytes(encrypted)
    store = V2Resources(tmp_path)
    result = store.objects()
    assert result['status'] == 'decoded'
    assert result['objects'] == [
        {'number': 0, 'name': 'key', 'initial_room': 0},
        {'number': 1, 'name': 'coin', 'initial_room': 255},
        {'number': 2, 'name': 'é', 'initial_room': 42},
    ]
    assert result['max_animated_objects'] == 16
    assert result['source']['sha256'] == sha256(encrypted).hexdigest()


def test_optional_sources_snapshot_and_caller_isolation(tmp_path):
    (tmp_path / 'WORDS.TOK').write_bytes(_words([('key', 7)]))
    (tmp_path / 'OBJECT').write_bytes(_objects([(b'key', 1)]))
    store = V2Resources(tmp_path)
    before = store.vocabulary(), store.objects(), store.manifest()
    (tmp_path / 'WORDS.TOK').unlink()
    (tmp_path / 'OBJECT').write_bytes(b'bad')
    external = store.vocabulary()
    external['groups'][0]['words'].clear()
    store.objects()['objects'].clear()
    assert (store.vocabulary(), store.objects(), store.manifest()) == before
    assert store.manifest()['read_counts'] == {'OBJECT': 1, 'WORDS.TOK': 1}
    assert {s['filename']: s['decode_status'] for s in store.manifest()['auxiliary']} == {
        'OBJECT': 'decoded', 'WORDS.TOK': 'decoded'}


def test_optional_missing_files_do_not_erase_resource_census(tmp_path):
    _containers(tmp_path)
    store = V2Resources(tmp_path)
    assert store.vocabulary()['status'] == store.objects()['status'] == 'absent'
    assert store.vocabulary()['groups'] == [] and store.objects()['objects'] == []
    assert len(store.resources('logic')) == 2


@pytest.mark.parametrize('filename', ['WORDS.TOK', 'OBJECT'])
def test_optional_oversize_file_remains_error(tmp_path, filename):
    (tmp_path / filename).write_bytes(b'\0' * 65536)
    store = V2Resources(tmp_path)
    result = store.vocabulary() if filename == 'WORDS.TOK' else store.objects()
    assert result['status'] == 'error' and 'limit' in result['error']


@pytest.mark.parametrize('filename', ['WORDS.TOK', 'OBJECT'])
def test_optional_ambiguous_case_remains_error(tmp_path, filename):
    (tmp_path / filename).write_bytes(b'original')
    other = tmp_path / filename.lower()
    other.write_bytes(b'duplicate')
    if other.samefile(tmp_path / filename):
        pytest.skip('case-sensitive filesystem required')
    store = V2Resources(tmp_path)
    result = store.vocabulary() if filename == 'WORDS.TOK' else store.objects()
    assert result['status'] == 'error' and 'ambiguous' in result['error'].lower()


def test_optional_mixed_case_sources_read_once(tmp_path, monkeypatch):
    (tmp_path / 'Words.Tok').write_bytes(_words([('key', 7)]))
    (tmp_path / 'Object').write_bytes(_objects([(b'key', 1)]))
    calls = []
    original = Path.open

    def counted(path, *args, **kwargs):
        if path.parent == tmp_path:
            calls.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', counted)
    store = V2Resources(tmp_path)
    assert store.vocabulary()['status'] == store.objects()['status'] == 'decoded'
    assert store.vocabulary()['status'] == store.objects()['status'] == 'decoded'
    assert sorted(calls) == ['Object', 'Words.Tok']


@pytest.mark.parametrize('mutate, reason', [
    (lambda data: b'x', 'header'),
    (lambda data: b'\0\x35' + data[2:], 'boundary'),
    (lambda data: b'\0\x34' + data[2:], 'letter'),
    (lambda data: data[:52] + b'\x01' + data[53:], 'prefix'),
    (lambda data: data[:-4], 'truncated'),
])
def test_bad_word_dictionary_is_explicit_without_partial_groups(tmp_path, mutate, reason):
    (tmp_path / 'WORDS.TOK').write_bytes(mutate(_words([('boat', 8)])))
    result = V2Resources(tmp_path).vocabulary()
    assert result['status'] == 'error' and reason in result['error'].lower()
    assert result['groups'] == []


def test_independent_word_encoding_vector(tmp_path):
    # At offset52: prefix0, "a" = (0x61 XOR 0x7f)|0x80 =0x9e,
    # big-endian group0x0123. The final zero terminates the file.
    (tmp_path / 'WORDS.TOK').write_bytes(b'\0\x34' + b'\0' * 50 + bytes.fromhex('009e012300'))
    result = V2Resources(tmp_path).vocabulary()
    assert result['status'] == 'decoded'
    assert result['groups'] == [{'number': 0x123, 'words': ['a'], 'role': 'word_group'}]


def test_same_letter_prefix_reset_is_retained_but_not_lookup_indexed(tmp_path):
    # Both words start with 'a', but the second prefix0 ends the engine's
    # indexed compression chain. Keep the second literal without claiming
    # that the alphabet index reaches it.
    records = bytes.fromhex('001e118b0011001e0c94001200')  # ant:17, ask:18
    (tmp_path / 'WORDS.TOK').write_bytes(b'\0\x34' + b'\0' * 50 + records)
    result = V2Resources(tmp_path).vocabulary()
    assert result['status'] == 'decoded'
    assert [e['word'] for e in result['entries']] == ['ant', 'ask']
    assert [e['lookup_indexed'] for e in result['entries']] == [True, False]


def test_plaintext_object_is_not_guessed_as_encrypted_profile(tmp_path):
    (tmp_path / 'OBJECT').write_bytes(bytes.fromhex('0300100300016b657900'))
    result = V2Resources(tmp_path).objects()
    assert result['status'] == 'error' and result['objects'] == []


def test_independent_object_cipher_and_relative_pointer_vector(tmp_path):
    # Encoded from 03 00 10 03 00 ff 6b 00: one record at3,
    # its name at3+3, initial room255, literal name "k".
    (tmp_path / 'OBJECT').write_bytes(bytes.fromhex('4276797020bb1e72'))
    result = V2Resources(tmp_path).objects()
    assert result['status'] == 'decoded'
    assert result['objects'] == [{'number': 0, 'name': 'k', 'initial_room': 255}]


@pytest.mark.parametrize('count, expected_status', [(256, 'decoded'), (257, 'error')])
def test_object_id_byte_boundary_with_shared_name_pointer(tmp_path, count, expected_status):
    # Aliases make this input small even at the object-count boundary. The
    # bound must precede potentially amplified name expansion.
    table_size = 3 * count
    record = table_size.to_bytes(2, 'little') + b'\xff'
    plain = table_size.to_bytes(2, 'little') + b'\x10' + record * count + b'item\0'
    encrypted = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(plain))
    (tmp_path / 'OBJECT').write_bytes(encrypted)
    result = V2Resources(tmp_path).objects()
    assert result['status'] == expected_status
    if count == 256:
        assert len(result['objects']) == 256
        assert result['objects'][-1] == {'number': 255, 'name': 'item', 'initial_room': 255}
    else:
        assert result['objects'] == [] and 'table' in result['error']


@pytest.mark.parametrize('plain, reason', [
    (b'', 'length'),
    (bytes.fromhex('040010'), 'table'),
    (bytes.fromhex('030010'), 'table'),
    (bytes.fromhex('03001000000061'), 'offset'),
    (bytes.fromhex('03001003000061'), 'terminated'),
])
def test_bad_object_inventory_is_explicit(tmp_path, plain, reason):
    encrypted = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(plain))
    (tmp_path / 'OBJECT').write_bytes(encrypted)
    result = V2Resources(tmp_path).objects()
    assert result['status'] == 'error' and reason in result['error'].lower()
    assert result['objects'] == []
