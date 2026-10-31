from fdisbull.cue import inspect_cue_path, parse_cue


def test_shared_file_and_generated_gaps(tmp_path):
    (tmp_path / 'disc.bin').write_bytes(bytes(2352 * 1000))
    cue = tmp_path / 'disc.cue'
    cue.write_text('''FILE "disc.bin" BINARY
 TRACK 01 MODE1/2352
 INDEX 01 00:00:00
 POSTGAP 00:00:10
 TRACK 02 AUDIO
 PREGAP 00:00:05
 INDEX 00 00:04:00
 INDEX 01 00:06:00
''')
    result = inspect_cue_path(cue)
    assert result['valid'] and result['complete']
    a, b = result['tracks']
    assert (a['file_end_sector'], a['program_sectors']) == (300, 300)
    assert (b['stored_pregap_sectors'], b['stored_sectors'], b['program_sectors']) == (150, 700, 550)
    assert (b['disc_start_lba'], b['disc_index01_lba'], b['disc_end_lba']) == (315, 465, 1015)


def test_separate_file_stored_pregap(tmp_path):
    (tmp_path / 'one.bin').write_bytes(bytes(2048 * 20))
    (tmp_path / 'two.bin').write_bytes(bytes(2352 * 750))
    cue = tmp_path / 'disc.cue'
    cue.write_text('''FILE "one.bin" BINARY
 TRACK 01 MODE1/2048
 INDEX 01 00:00:00
FILE "two.bin" BINARY
 TRACK 02 AUDIO
 INDEX 00 00:00:00
 INDEX 01 00:02:00
''')
    result = inspect_cue_path(cue)
    assert result['valid']
    track = result['tracks'][1]
    assert (track['stored_sectors'], track['program_sectors'], track['disc_index01_lba']) == (750, 600, 170)


def test_reject_unsafe_and_unsupported(tmp_path):
    for ref in ('../outside.bin', '/etc/passwd', 'C:/secret.bin', '//host/share'):
        assert not parse_cue(f'FILE "{ref}" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00')['valid']
    for extra in ('INDEX 02 00:00:01', 'FLAGS DCP', 'PREGAP 00:60:00'):
        assert not parse_cue(f'FILE "x" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n {extra}')['valid']
    (tmp_path / 'link').symlink_to('/etc/passwd')
    cue = tmp_path / 'd.cue'
    cue.write_text('FILE "link" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00')
    assert not inspect_cue_path(cue)['valid']


def test_bounds_and_bad_layout(tmp_path):
    assert not parse_cue('x' * (1024 * 1024 + 1))['valid']
    assert not parse_cue('FILE "x" BINARY\n TRACK 01 AUDIO\n INDEX 00 00:02:00\n INDEX 01 00:01:00')['valid']
    (tmp_path / 'x').write_bytes(bytes(2352 * 10))
    cue = tmp_path / 'd.cue'
    cue.write_text('FILE "x" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n TRACK 02 MODE1/2048\n INDEX 01 00:00:01')
    assert not inspect_cue_path(cue)['valid']


def test_file_prefix_rejected_and_identities_recorded(tmp_path):
    import hashlib

    image = tmp_path / 'one.bin'
    image.write_bytes(bytes(2352 * 10))
    cue = tmp_path / 'disc.cue'
    cue.write_text('FILE "one.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:01\n')
    result = inspect_cue_path(cue)
    assert not result['valid'] and 'prefix' in result['errors'][0]
    cue.write_text('FILE "one.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n')
    result = inspect_cue_path(cue)
    assert result['valid']
    assert result['cue_sha256'] == hashlib.sha256(cue.read_bytes()).hexdigest()
    identity = result['tracks'][0]['file_identity']
    info = image.stat()
    assert identity == {'dev': info.st_dev, 'ino': info.st_ino, 'size': info.st_size,
                        'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}
    assert result['cue_identity']['ino'] == cue.stat().st_ino
