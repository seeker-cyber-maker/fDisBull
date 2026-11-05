"""Authored header envelopes: recognition never certifies payloads or playback."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct

import pytest

from fdisbull.format_registry import FormatCatalog, format_catalog, identify_file


def write(tmp_path, data, name='misleading.bin'):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def smk(marker=b'SMK2'):
    header = bytearray(104)
    header[:4] = marker
    struct.pack_into('<IIIiI', header, 4, 320, 200, 2, 67, 0)
    struct.pack_into('<I', header, 72, 22050 | 0x90000000)
    # Only a header/table envelope, not a decodable authored movie.
    return bytes(header) + struct.pack('<II', 4, 4) + bytes(2) + bytes(8)


def mz():
    return struct.pack('<14H', 0x5a4d, 36, 1, 0, 2, 0, 0, 0, 0, 0, 0, 0, 28, 0) + bytes(4) + b'CODE' + b'OPAQUE_SENTINEL'


def iso_descriptor(count=100):
    p = bytearray(2048)
    p[:7] = b'\x01CD001\x01'
    p[40:47] = b'AUTHORD'
    for offset, number, width in ((80,count,4),(128,2048,2),(158,20,4),(166,2048,4)):
        p[offset:offset+width] = number.to_bytes(width,'little')
        p[offset+width:offset+2*width] = number.to_bytes(width,'big')
    p[156], p[181] = 34, 2
    p[188:190] = b'\x01\x00'
    return bytes(p)


def result(path, **options):
    return identify_file(path, **options)['identification']


def test_recognition_is_not_extension_or_codec_validation(tmp_path):
    source = write(tmp_path, smk(), 'movie.exe')
    report = identify_file(source)
    found = report['identification']
    assert found['format_id'] == 'smacker'
    assert found['header_valid'] and found['status'] == 'recognized-header'
    assert found['metadata']['logical_frames'] == 2
    assert found['metadata']['audio_tracks'] == [dict(index=0,rate=22050,flags=0x90)]
    assert found['metadata']['frame_size_table_checked']
    assert not found['full_decode'] and not found['native_runtime_tested']
    assert report['source']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert not report['input_executed'] and not report['source_bytes_persisted']
    unknown = result(write(tmp_path,b'No movie header here','unknown.smk'))
    assert unknown['status'] == 'unknown' and not unknown['recognized']
    com = result(write(tmp_path,b'\xc3','program.com'))
    assert com['format_id'] is None and com['architecture'] is None


def test_declared_dos_overlay_number_is_header_evidence_not_directory_recovery(tmp_path):
    data = bytearray(mz())
    struct.pack_into('<H', data, 26, 3)
    found = result(write(tmp_path, data))
    envelope = found['mz_envelope']
    assert envelope['declared_overlay_number'] == 3
    assert envelope['tail_offset'] == 36 and envelope['trailing_bytes'] == len(data) - 36
    assert envelope['overlays_recovered'] is False
    assert envelope['tail_structure'] == 'opaque'
    definition = next(row for row in format_catalog()['formats'] if row['format_id'] == 'dos-mz')
    assert any(row['name'] == 'overlay_number' and row['offset'] == 26 for row in definition['header_fields'])


def test_truncated_and_unsupported_smk_are_explicit(tmp_path):
    assert result(write(tmp_path,b'SMK2'))['status'] == 'recognized-invalid'
    data = bytearray(smk())
    struct.pack_into('<I',data,104,1_000_000)
    assert not result(write(tmp_path,data))['header_valid']
    found = result(write(tmp_path,smk(b'SMK4')))
    assert found['format_id']=='smacker' and found['header_valid']
    assert any('SMK4' in warning for warning in found['warnings'])


def test_zero_smk_rate_is_a_header_fact_not_an_invented_playback_default(tmp_path):
    data=bytearray(smk());struct.pack_into('<i',data,16,0)
    found=result(write(tmp_path,data))
    assert found['header_valid'] and found['metadata']['rate_field']==0
    assert any('decoder-specific' in warning for warning in found['warnings'])
    assert not found['native_runtime_tested']
    struct.pack_into('<i',data,16,-2147483648)
    assert result(write(tmp_path,data))['status']=='recognized-invalid'


@pytest.mark.parametrize('kind,data', [
    ('vdx', b'\x67\x92'+bytes(4)+struct.pack('<H',15)+b'\x20\0'+struct.pack('<I',0)+bytes(2)),
    ('roq', b'\x84\x10'+b'\xff'*4+struct.pack('<H',30)),
    ('riff-wave', b'RIFF'+struct.pack('<I',4)+b'WAVE'),
    ('riff-avi', b'RIFF'+struct.pack('<I',4)+b'AVI '),
    ('riff', b'RIFF'+struct.pack('<I',4)+b'ZZZZ'),
    ('zip', b'PK\x05\x06'+bytes(18)),
])
def test_header_only_formats_and_unknown_riff_forms(tmp_path,kind,data):
    found = result(write(tmp_path,data))
    assert found['format_id']==kind and found['header_valid']
    assert not found['full_decode'] and not found['native_runtime_tested']
    assert any(m['module_id']=='format-headers' for m in found['decoder_modules'])


def test_flic_custom_length_is_reported_without_inventing_companions(tmp_path):
    data = bytearray(136)
    struct.pack_into('<I5H',data,0,128,0xaf12,1,320,85,8)
    found = result(write(tmp_path,data,'custom.VID'))
    assert found['format_id']=='flic' and found['metadata']['variant']=='FLC'
    assert found['metadata']['declared_bytes']==128
    assert found['warnings'] and not found['full_decode']
    struct.pack_into('<I',data,0,200)
    assert result(write(tmp_path,data))['status']=='recognized-invalid'


def test_bullfrog_compact_flic_does_not_invent_standard_depth_or_file_size(tmp_path):
    # Authored compact header and two empty 16-byte frame chunks; no game bytes.
    header=struct.pack('<I4H',12,0xaf12,2,16,8)
    frame=struct.pack('<IHH8s',16,0xf1fa,0,bytes(8))
    found=result(write(tmp_path,header+frame+frame,'compact.dat'))
    assert found['format_id']=='bullfrog-flic12' and found['header_valid']
    assert found['metadata']['header_bytes']==12
    assert found['metadata']['size_field']==12
    assert found['metadata']['width']==16 and found['metadata']['height']==8
    assert found['metadata']['depth'] is None
    assert found['metadata']['first_frame_bytes']==16
    assert not found['full_decode'] and not found['native_runtime_tested']
    assert any(m['module_id']=='format-headers' for m in found['decoder_modules'])


def test_compact_flic_first_frame_overflow_is_not_accepted(tmp_path):
    data=struct.pack('<I4H',12,0xaf12,1,16,8)+struct.pack('<IHH8s',200,0xf1fa,0,bytes(8))
    found=result(write(tmp_path,data))
    assert found['format_id']=='bullfrog-flic12' and not found['header_valid']
    assert 'extent' in found['warnings'][-1]


def test_mp3_requires_two_headers_and_id3_alone_is_metadata(tmp_path):
    header = b'\xff\xfb\x90\0'  # MPEG1 LayerIII 128kb/s 44.1kHz, 417-byte frame.
    assert result(write(tmp_path,header+bytes(413)+header))['format_id']=='mp3'
    assert result(write(tmp_path,header))['format_id'] is None
    tag = b'ID3\x04\0\0'+bytes(4)
    assert result(write(tmp_path,tag))['format_id']=='id3'
    found = result(write(tmp_path,tag+header+bytes(413)+header))
    assert found['format_id']=='mp3' and found['metadata']['audio_offset']==10
    invalid = b'ID3\x04\0\0\x80\0\0\0'
    assert result(write(tmp_path,invalid))['status']=='recognized-invalid'


@pytest.mark.parametrize('kind,data,geometry',[
    ('png', b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',640,480)+bytes([8,2,0,0,0])+bytes(4), (640,480)),
    ('gif', b'GIF89a'+struct.pack('<HH',320,200)+bytes(3), (320,200)),
    ('bmp', b'BM'+struct.pack('<I',62)+bytes(4)+struct.pack('<I',54)+struct.pack('<IiiHHII',40,2,-1,1,24,0,8)+bytes(16)+bytes(8),(2,1)),
    ('jpeg', b'\xff\xd8\xff\xc0'+struct.pack('>HBHHB',17,8,240,320,3)+bytes([1,0x11,0,2,0x11,0,3,0x11,0]),(320,240)),
])
def test_image_geometry_is_header_only_and_links_available_reader(tmp_path,kind,data,geometry):
    found=result(write(tmp_path,data,'image.not-an-image-extension'))
    assert found['format_id']==kind and found['header_valid']
    assert (found['metadata']['width'],found['metadata']['height'])==geometry
    assert not found['full_decode'] and not found['native_runtime_tested']
    assert any(m['module_id']=='format-headers' for m in found['decoder_modules'])
    if kind=='png':assert found['metadata']['crc_checked'] is False


def test_image_truncation_and_explicit_bounded_unsupported_layout(tmp_path):
    assert result(write(tmp_path,b'\x89PNG\r\n\x1a\n'))['status']=='recognized-invalid'
    assert result(write(tmp_path,b'GIF87a'))['status']=='recognized-invalid'
    assert result(write(tmp_path,b'BM'))['status']=='recognized-invalid'
    assert result(write(tmp_path,b'\xff\xd8'))['status']=='recognized-invalid'
    bmp=b'BM'+struct.pack('<I',30)+bytes(4)+struct.pack('<II',30,16)+bytes(12)
    assert result(write(tmp_path,bmp))['status']=='recognized-unsupported-layout'
    jpeg=b'\xff\xd8\xff\xe0'+struct.pack('>H',65535)+bytes(65533)
    found=result(write(tmp_path,jpeg))
    assert found['status']=='recognized-header-limit' and found['header_valid'] is None


@pytest.mark.parametrize('raw',[False,True])
def test_iso_descriptor_is_sampled_without_reading_file_payloads(tmp_path,raw):
    sector = 2352 if raw else 2048
    source = tmp_path/'disc.unknown'
    with source.open('wb') as stream:
        stream.truncate(100*sector)
        if raw:
            framing = b'\0'+b'\xff'*10+b'\0'+bytes(3)+b'\x01'
            stream.seek(0);stream.write(framing)
            stream.seek(16*sector);stream.write(framing)
        stream.seek(16*sector+(16 if raw else 0));stream.write(iso_descriptor())
    report = identify_file(source)
    found = report['identification']
    assert found['format_id']=='iso9660' and found['header_valid']
    assert found['metadata']['sector_bytes']==sector
    assert not found['metadata']['primary_descriptor']['directory_traversal']
    assert report['source']['sha256'] is None
    assert report['source']['bytes_read'] <= 128*1024+2352
    assert report['source']['size']==100*sector


def test_existing_binary_reader_views_and_opaque_mz_tail(tmp_path):
    from fdisbull.inspection import identify_header
    source = write(tmp_path,mz())
    found = result(source)
    assert found['format_id']=='dos-mz'
    assert found['architecture']['arch']=='x86' and found['architecture']['bits']==16
    assert found['image_views']==identify_header(source.read_bytes())['image_views']
    tail = found['mz_envelope']
    assert tail['tail_offset']==36 and tail['trailing_bytes']==15
    assert tail['tail_structure']=='opaque' and not tail['overlays_recovered']
    assert any(m['module_id']=='mz-envelope' for m in found['decoder_modules'])


def test_native_reader_budget_does_not_invent_loadable_large_views(tmp_path):
    source = write(tmp_path,mz()+bytes(8192))
    found = result(source,max_binary_bytes=4096)
    assert found['status']=='recognized-unsupported-size' and found['header_valid'] is None
    assert 'image_views' not in found
    assert found['mz_envelope']['tail_structure']=='opaque'
    assert found['architecture']['arch']=='x86' and found['architecture']['bits']==16


def test_oversized_pe_still_reports_observed_cpu_fields(tmp_path):
    from test_inspection import pe64
    source=write(tmp_path,pe64()+bytes(8192))
    found=result(source,max_binary_bytes=4096)
    assert found['format_id']=='pe' and found['status']=='recognized-unsupported-size'
    assert found['architecture']['arch']=='x86' and found['architecture']['bits']==64
    assert found['header_valid'] is None and 'image_views' not in found


def test_persistent_catalog_reopens_idempotently_without_source_payload(tmp_path):
    catalog = tmp_path/'formats.sqlite'
    source = write(tmp_path,mz())
    identify_file(source,catalog_path=catalog)
    before = format_catalog(catalog_path=catalog)
    after = format_catalog(catalog_path=catalog)
    assert before==after and before['schema_version']==1
    definitions = {d['format_id']:d for d in before['formats']}
    assert definitions['smacker']['header_fields'][0]['offset']==4
    assert any(f['name']=='audio_rates_flags' and f['offset']==72 for f in definitions['smacker']['header_fields'])
    assert any(b['format_id']=='dos-mz' and b['module_id']=='mz-envelope' for b in before['bindings'])
    assert b'OPAQUE_SENTINEL' not in catalog.read_bytes()
    assert str(source).encode() not in catalog.read_bytes()
    assert before['contains_file_payloads'] is False and not before['dynamic_plugins_loaded']
    assert before['inspected_source_bytes_persisted'] is False


def test_future_records_are_preserved_but_never_loaded_as_plugins(tmp_path):
    catalog = tmp_path/'formats.sqlite'
    format_catalog(catalog_path=catalog)
    extra = dict(module_id='untrusted-future',revision=1,api='os.system',implemented=True,capabilities=['execute'])
    with sqlite3.connect(catalog) as db:
        db.execute('INSERT INTO format_decoder_modules VALUES (?,?,?)',('untrusted-future',1,json.dumps(extra)))
        db.execute('INSERT INTO format_decoder_links VALUES (?,?,?,?)',('smacker',1,'untrusted-future',1))
    found = result(write(tmp_path,smk()),catalog_path=catalog)
    module = next(m for m in found['decoder_modules'] if m['module_id']=='untrusted-future')
    assert not module['implemented'] and not module['binding_verified'] and module['declared_implemented']
    with sqlite3.connect(catalog) as db:
        assert json.loads(db.execute('SELECT record_json FROM format_decoder_modules WHERE module_id=?',('untrusted-future',)).fetchone()[0])==extra


def test_constructor_rejects_oversized_conflicting_row_before_loading_it(tmp_path):
    catalog=tmp_path/'large.sqlite'
    format_catalog(catalog_path=catalog)
    encoded=json.dumps({'data_base64':'x'*200_000})
    with sqlite3.connect(catalog) as db:
        db.execute('UPDATE format_definitions SET record_json=? WHERE format_id=?',(encoded,'smacker'))
    frozen=catalog.read_bytes()
    with pytest.raises(ValueError,match='metadata budget exceeded'):
        FormatCatalog(catalog)
    assert catalog.read_bytes()==frozen


def test_snapshot_preflights_large_custom_row_before_any_json_materialization(tmp_path,monkeypatch):
    catalog=FormatCatalog(tmp_path/'large-snapshot.sqlite')
    try:
        assert catalog.db.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)<=128*1024
        custom=json.dumps(dict(format_id='large-custom',revision=1,padding='x'*70_000))
        with sqlite3.connect(catalog.path) as db:
            db.execute('INSERT INTO format_definitions VALUES (?,?,?)',('large-custom',1,custom))
        def forbidden(_):raise AssertionError('JSON materialization preceded budget preflight')
        monkeypatch.setattr('fdisbull.format_registry.json.loads',forbidden)
        with pytest.raises(ValueError,match='metadata budget exceeded'):
            catalog.snapshot()
        with sqlite3.connect(catalog.path) as db:
            assert db.execute('SELECT length(record_json) FROM format_definitions WHERE format_id=?',('large-custom',)).fetchone()[0]==len(custom)
    finally:catalog.close()


def test_snapshot_limits_combined_record_count_before_decoding_json():
    catalog=FormatCatalog()
    try:
        with catalog.db:
            catalog.db.executemany('INSERT INTO format_definitions VALUES (?,?,?)',
                [(f'custom-{i}',1,json.dumps(dict(format_id=f'custom-{i}',revision=1))) for i in range(4097)])
        with pytest.raises(ValueError,match='metadata budget exceeded'):
            catalog.snapshot()
    finally:catalog.close()


def test_snapshot_limits_links_before_materialization():
    catalog=FormatCatalog()
    try:
        with catalog.db:
            catalog.db.executemany('INSERT INTO format_definitions VALUES (?,?,?)',
                [(f'f-{i}',1,json.dumps(dict(format_id=f'f-{i}',revision=1))) for i in range(129)])
            catalog.db.executemany('INSERT INTO format_decoder_modules VALUES (?,?,?)',
                [(f'm-{i}',1,json.dumps(dict(module_id=f'm-{i}',revision=1))) for i in range(129)])
            catalog.db.executemany('INSERT INTO format_decoder_links VALUES (?,?,?,?)',
                ((f'f-{a}',1,f'm-{b}',1) for a in range(129) for b in range(129)))
        with pytest.raises(ValueError,match='link budget exceeded'):
            catalog.snapshot()
    finally:catalog.close()


def test_text_link_revision_is_rejected_before_json_or_link_materialization(tmp_path,monkeypatch):
    path=tmp_path/'text-link-revision.sqlite'
    catalog=FormatCatalog(path)
    try:
        # INTEGER affinity does not stop an external SQLite writer storing TEXT.
        # A large revision must not bypass identifier/document byte budgets.
        with sqlite3.connect(path) as db:
            db.execute('INSERT INTO format_decoder_links VALUES (?,?,?,?)',('smacker','x'*70_000,'format-headers',1))
        frozen=path.read_bytes()
        def forbidden(_):raise AssertionError('Materialization preceded type/revision preflight')
        monkeypatch.setattr('fdisbull.format_registry.json.loads',forbidden)
        with pytest.raises(ValueError,match='link revisions'):
            catalog.snapshot()
        with pytest.raises(ValueError,match='link revisions'):
            FormatCatalog(path)
        assert path.read_bytes()==frozen
    finally:catalog.close()


def test_non_integer_record_revision_is_refused_without_rewriting(tmp_path):
    path=tmp_path/'text-record-revision.sqlite'
    format_catalog(catalog_path=path)
    value=dict(format_id='future-invalid-revision',revision='future')
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO format_definitions VALUES (?,?,?)',('future-invalid-revision','future',json.dumps(value)))
    frozen=path.read_bytes()
    with pytest.raises(ValueError,match='positive integer revisions'):
        format_catalog(catalog_path=path)
    assert path.read_bytes()==frozen


@pytest.mark.parametrize('table,key',[('format_definitions','format_id'),('format_decoder_modules','module_id')])
def test_custom_record_content_is_unknown_and_source_persistence_claim_is_scoped(tmp_path,table,key):
    path=tmp_path/'custom-content.sqlite'
    format_catalog(catalog_path=path)
    custom={key:'custom-with-payload', 'revision':1,'data_base64':'YWJj'}
    with sqlite3.connect(path) as db:
        db.execute(f'INSERT INTO {table} VALUES (?,?,?)',('custom-with-payload',1,json.dumps(custom)))
        if key=='module_id':
            db.execute('INSERT INTO format_decoder_links VALUES (?,?,?,?)',('smacker',1,'custom-with-payload',1))
    report=format_catalog(catalog_path=path)
    assert report['contains_file_payloads'] is None
    assert report['catalog_content_qualification']=='custom-record-content-unverified'
    assert report['inspected_source_bytes_persisted'] is False
    records=report['formats' if key=='format_id' else 'modules']
    found=next(record for record in records if record[key]=='custom-with-payload')
    assert found['data_base64']=='YWJj'
    if key=='module_id':assert not found['implemented'] and not found['binding_verified']
    file_report=identify_file(write(tmp_path,smk()),catalog_path=path)
    assert file_report['catalog']['contains_file_payloads'] is None
    assert file_report['catalog']['content_qualification']=='custom-record-content-unverified'
    assert file_report['inspected_source_bytes_persisted'] is False
    assert file_report['source_bytes_persisted'] is False
    if key=='module_id':
        linked=next(m for m in file_report['identification']['decoder_modules'] if m['module_id']=='custom-with-payload')
        assert linked['data_base64']=='YWJj' and not linked['implemented']
    with sqlite3.connect(path) as db:
        assert json.loads(db.execute(f'SELECT record_json FROM {table} WHERE {key}=?',('custom-with-payload',)).fetchone()[0])==custom


def test_catalog_conflicts_and_future_schema_fail_without_rewriting(tmp_path):
    catalog = tmp_path/'formats.sqlite'
    format_catalog(catalog_path=catalog)
    with sqlite3.connect(catalog) as db:
        db.execute('UPDATE format_definitions SET record_json=? WHERE format_id=?',('{}','smacker'))
    with pytest.raises(ValueError,match='Conflicting immutable'):
        format_catalog(catalog_path=catalog)
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT record_json FROM format_definitions WHERE format_id=?',('smacker',)).fetchone()[0]=='{}'
    future = tmp_path/'future.sqlite'
    with sqlite3.connect(future) as db:
        db.execute('CREATE TABLE format_catalog_meta(schema_version INTEGER)')
        db.execute('INSERT INTO format_catalog_meta VALUES (99)')
    frozen = future.read_bytes()
    with pytest.raises(ValueError,match='schema version'):
        format_catalog(catalog_path=future)
    assert future.read_bytes()==frozen


def test_source_catalog_aliases_and_special_files_are_refused(tmp_path):
    source = write(tmp_path,smk())
    with pytest.raises(ValueError,match='different files'):
        identify_file(source,catalog_path=source)
    alias = tmp_path/'catalog-link';alias.symlink_to(source)
    with pytest.raises(ValueError):
        format_catalog(catalog_path=alias)
    with pytest.raises(ValueError,match='regular file'):
        identify_file('/dev/null')
    linked_source = tmp_path/'movie-link';linked_source.symlink_to(source)
    assert result(linked_source)['format_id']=='smacker'


def test_mid_read_source_change_is_not_accepted(tmp_path,monkeypatch):
    from fdisbull.format_registry import _Reader
    source = write(tmp_path,smk())
    original = _Reader.read
    changed = False
    def mutate(reader,offset,count):
        nonlocal changed
        value = original(reader,offset,count)
        if not changed:
            with source.open('ab') as stream:stream.write(b'changed')
            changed = True
        return value
    monkeypatch.setattr(_Reader,'read',mutate)
    with pytest.raises(ValueError,match='changed during'):
        identify_file(source)
