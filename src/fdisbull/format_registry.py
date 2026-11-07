"""Bounded file identification and an inert, versioned format-module catalog.

Catalog records describe implemented readers. They are never imported, evaluated
or used as executable parsing rules. Source bytes are not written to the catalog.
Header recognition, structural checks, decoding and native use are separate facts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct

SCHEMA_VERSION = 1
MAX_BINARY_BYTES = 64 * 1024 * 1024
PREFIX_BYTES = 128 * 1024
MAX_TABLE_BYTES = 64 * 1024
MAX_CATALOG_RECORD_BYTES = 64 * 1024
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_CATALOG_RECORDS = 4096
MAX_CATALOG_LINKS = 16384
MAX_IDENTIFY_READ_BYTES = MAX_BINARY_BYTES + PREFIX_BYTES + 2 * MAX_TABLE_BYTES + 4096
_SYNC = b'\x00' + b'\xff' * 10 + b'\x00'


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _field(name, offset, kind, meaning):
    return dict(name=name, offset=offset, type=kind, meaning=meaning)


def _definition(identifier, name, category, signatures, fields, *, endian=None,
                limitations=(), provenance=()):
    return dict(format_id=identifier, revision=1, name=name, category=category,
                endianness=endian, signatures=signatures, header_fields=fields,
                limitations=list(limitations), provenance=list(provenance))


def _magic(offset, value):
    return dict(offset=offset, hex=value.hex())


def _builtins():
    """Small descriptive records; parsing stays in explicitly shipped Python."""
    native = []
    specs = [
        ('dos-mz', 'DOS MZ', [_magic(0, b'MZ')], 'little',
         [_field('last_page_bytes', 2, 'u16le', 'DOS load-image end'),
          _field('pages', 4, 'u16le', '512-byte pages'),
          _field('header_paragraphs', 8, 'u16le', '16-byte paragraphs'),
          _field('overlay_number', 26, 'u16le', 'Declared DOS overlay number; zero names the main program, not an absence-of-overlays proof'),
          _field('secondary_header', 60, 'u32le', 'Only independent of relocation words')]),
        ('pe', 'PE32 / PE32+', [_magic('MZ.e_lfanew', b'PE\0\0')], 'little',
         [_field('machine', 'secondary+4', 'u16le', 'COFF machine'),
          _field('optional_magic', 'secondary+24', 'u16le', '0x10b=PE32, 0x20b=PE32+')]),
        ('ne', 'Win16 NE', [_magic('MZ.e_lfanew', b'NE')], 'little',
         [_field('segment_count', 'secondary+28', 'u16le', 'Logical segment count')]),
        ('le', 'LE linear executable', [_magic(0, b'LE'), _magic('MZ.e_lfanew', b'LE')], 'little',
         [_field('page_size', 'secondary+40', 'u32le', 'Logical page size'),
          _field('object_count', 'secondary+68', 'u32le', 'Object table entries')]),
        ('lx', 'LX linear executable', [_magic('MZ.e_lfanew', b'LX')], 'little', []),
        ('elf', 'ELF', [_magic(0, b'\x7fELF')], 'declared',
         [_field('class', 4, 'u8', '1=32 bit, 2=64 bit'),
          _field('data', 5, 'u8', '1=little, 2=big endian'),
          _field('machine', 18, 'u16:declared-endian', 'Architecture')]),
        ('macho', 'Mach-O', [_magic(0, m) for m in (b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf')], 'declared',
         [_field('cpu_type', 4, 'u32:declared-endian', 'CPU and ABI width')]),
        ('macho-fat', 'Universal Mach-O', [_magic(0, m) for m in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')], 'declared',
         [_field('slice_count', 4, 'u32:declared-endian', 'Independently selected architectures')]),
        ('ail', 'Miles AIL driver', [_magic(2, b'Copyright (C) ')], 'little',
         [_field('directory', 0, 'u16le', 'Also requires Miles/John Miles family notice and bounded exports')]),
        ('nes-ines', 'NES iNES / NES 2.0', [_magic(0, b'NES\x1a')], 'little',
         [_field('prg_units', 4, 'u8', '16KiB units, variant-dependent'), _field('flags', 6, 'bytes[2]', 'Mapper and variant flags')]),
        ('snes-rom', 'SNES header candidate', [], 'little',
         [_field('map_mode', '0x7fc0/0xffc0/0x40ffc0 + copier-prefix + 21', 'u8', 'Multiple independent signals required'),
          _field('checksum_pair', 'header+28', 'u16le[2]', 'Complement pair, not checksum verification')]),
        ('sega-genesis', 'Genesis / Mega Drive cartridge', [_magic(256, b'SEGA')], 'big',
         [_field('rom_start', 416, 'u32be', 'Declared ROM range'), _field('rom_end', 420, 'u32be', 'Inclusive declared ROM end')]),
        ('sega-sms', 'Master System / Game Gear cartridge', [_magic('0x1ff0/0x3ff0/0x7ff0', b'TMR SEGA')], 'little',
         [_field('region_size', 'header+15', 'u8', 'Packed region and capacity')]),
        ('sega-disc', 'Sega CD / Saturn disc', [_magic('user-sector-zero', b'SEGA SEGASATURN '), _magic('user-sector-zero', b'SEGADISCSYSTEM  ')], 'mixed',
         [_field('platform', 'sector-zero system descriptor', 'ascii', 'Header claims, not boot or mapping proof')]),
    ]
    for ident, name, signatures, endian, fields in specs:
        native.append(_definition(ident, name, 'executable' if ident not in ('nes-ines', 'snes-rom', 'sega-genesis', 'sega-sms', 'sega-disc') else 'console-media',
            signatures, fields, endian=endian,
            limitations=['Existing bounded native/ROM reader owns architecture and view validation; no execution or complete recovery.'],
            provenance=['src/fdisbull/inspection.py', 'src/fdisbull/image_views.py', 'src/fdisbull/roms.py']))
    media = [
        _definition('smacker', 'Smacker SMK2 / SMK4', 'video', [_magic(0, b'SMK2'), _magic(0, b'SMK4')],
            [_field('width', 4, 'u32le', 'Indexed pixel width'), _field('height', 8, 'u32le', 'Indexed pixel height'),
             _field('frames', 12, 'u32le', 'Logical frame count'), _field('frame_rate', 16, 'i32le', 'Positive milliseconds or negative 1/100000 second units; zero timing is decoder-specific'),
             _field('flags', 20, 'u32le', 'Ring/interlace/double flags'), _field('tree_bytes', 52, 'u32le', 'Compressed Huffman table bytes'),
             _field('audio_rates_flags', 72, 'u32le[7]', 'Low24 rate, high8 audio flags'), _field('frame_sizes', 104, 'u32le[physical_frames]', 'Low2 bits are flags')],
            endian='little', limitations=['SMK4 recognized; native framing is restricted by the explicit SMK2 module profile.', 'Header/table checks do not decode palettes, trees, frames or audio.'],
            provenance=['https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/smacker.c', 'https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/smacker.c']),
        _definition('vdx', 'Groovie VDX', 'video', [_magic(0, b'\x67\x92')],
            [_field('frame_rate', 6, 'u16le', 'Groovie frame-rate field'), _field('chunk_type', 8, 'u8', 'Replay/still/delta/audio resource'),
             _field('chunk_size', 10, 'u32le', 'First resource payload length')], endian='little',
            limitations=['Standalone VDX header candidate only; no GJD/GROOVIE archive traversal, delta/LZSS/audio decoder or rewriting.'],
            provenance=['https://github.com/scummvm/scummvm/blob/master/engines/groovie/video/vdx.cpp']),
        _definition('roq', 'RoQ', 'video', [_magic(0, b'\x84\x10\xff\xff\xff\xff'), _magic(0, b'\x84\x10\0\0\0\0')],
            [_field('size_marker', 2, 'u32le', '0xffffffff or supported Groovie zero marker'), _field('frame_rate', 6, 'u16le', 'Declared rate; zero marker/rate variant means 30')],
            endian='little', limitations=['Signature and rate only; no codebook/video/audio/chunk decoder.'],
            provenance=['https://github.com/scummvm/scummvm/blob/master/engines/groovie/video/roq.cpp']),
        _definition('flic', 'Autodesk FLI / FLC', 'animation', [_magic(4, b'\x11\xaf'), _magic(4, b'\x12\xaf')],
            [_field('declared_bytes', 0, 'u32le', 'Header-declared size, compared with actual source'),
             _field('frames', 6, 'u16le', 'Frame count'), _field('width', 8, 'u16le', 'Width'),
             _field('height', 10, 'u16le', 'Height'), _field('depth', 12, 'u16le', 'Indexed format normally8 bits')],
            endian='little', limitations=['FLC signature alone does not establish custom VID/IDX semantics or safe rewriting.'],
            provenance=['https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/flic.c']),
        _definition('bullfrog-flic12', 'Bullfrog compact FLIC header', 'animation',
            [_magic(4,b'\x12\xaf'),_magic(16,b'\xfa\xf1')],
            [_field('size_field',0,'u32le','Legacy field; not assumed to be complete file length'),
             _field('frames',6,'u16le','Declared frame count'),_field('width',8,'u16le','Width'),
             _field('height',10,'u16le','Height'),_field('first_frame_bytes',12,'u32le','First chunk size, not color depth'),
             _field('first_frame_type',16,'u16le','0xf1fa frame chunk'),_field('first_frame_subchunks',18,'u16le','Declared nested chunks')],
            endian='little',limitations=['Twelve-byte header and first frame extent only; no color-depth field, frame/subchunk decoding, complete frame census or native playback claim.'],
            provenance=['https://github.com/swfans/syndwarsfx/blob/cd03fb2c5a50a5ec8002f2b45252475ab39cbf6e/bflibrary/include/bfflic.h#L54-L76',
                        'https://github.com/swfans/syndwarsfx/blob/cd03fb2c5a50a5ec8002f2b45252475ab39cbf6e/bflibrary/src/general/gflicply.c#L539-L564']),
        _definition('riff-wave', 'RIFF WAVE', 'audio', [_magic(0, b'RIFF'), _magic(8, b'WAVE')],
            [_field('riff_bytes', 4, 'u32le', 'Container bytes excluding first8'), _field('form', 8, 'fourcc', 'WAVE')], endian='little',
            limitations=['RIFF envelope only; fmt/data chunks and samples not decoded.'], provenance=['https://www.mmsp.ece.mcgill.ca/Documents/AudioFormats/WAVE/WAVE.html']),
        _definition('riff-avi', 'RIFF AVI', 'video', [_magic(0, b'RIFF'), _magic(8, b'AVI ')],
            [_field('riff_bytes', 4, 'u32le', 'This RIFF segment bytes excluding first8'), _field('form', 8, 'fourcc', 'AVI ')], endian='little',
            limitations=['RIFF envelope only; OpenDML segments, stream/index integrity and codecs not decoded.'], provenance=['src/fdisbull/capture_audit.py']),
        _definition('riff', 'Other RIFF form', 'container', [_magic(0, b'RIFF')], [_field('form', 8, 'fourcc', 'Unrecognized RIFF subtype')], endian='little',
            limitations=['Recognized unsupported subtype.'], provenance=['https://www.loc.gov/preservation/digital/formats/fdd/fdd000025.shtml']),
        _definition('id3', 'ID3v2 metadata', 'metadata', [_magic(0, b'ID3')],
            [_field('version', 3, 'u8', 'ID3 major version'), _field('flags', 5, 'u8', 'Version-specific flags'), _field('tag_bytes', 6, 'synchsafe-u28', 'Tag size excluding first10')],
            limitations=['Metadata is not proof of MPEG audio; no tag-frame or text extraction.'], provenance=['https://id3.org/id3v2.4.0-structure']),
        _definition('mp3', 'MPEG Layer III audio', 'audio', [dict(offset='after optional ID3v2 tag', mask_hex='ffe00000', value_hex='ffe00000')],
            [_field('mpeg_header', 'audio-start', 'u32be/bitfields', 'Version/layer/bitrate/rate/padding'), _field('next_header', 'audio-start+frame_bytes', 'u32be/bitfields', 'Consistent second frame required')],
            endian='big', limitations=['Two MPEG LayerIII frame headers only; no CRC, complete stream, gapless timing or audio decode.'], provenance=['https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/mpegaudiodecheader.c']),
        _definition('iso9660', 'ISO 9660 data volume', 'disc', [_magic('16*2048+1 or16*2352+16+1', b'CD001')],
            [_field('volume_sectors', 'PVD+80', 'u32le/u32be', 'Dual-endian agreement'), _field('block_bytes', 'PVD+128', 'u16le/u16be', '2048-byte logical blocks')],
            endian='dual', limitations=['Sector16 primary descriptor only; no directory traversal, track/audio TOC or complete filesystem validation.'], provenance=['src/fdisbull/rom_disc.py', 'https://ecma-international.org/publications-and-standards/standards/ecma-119/']),
        _definition('zip', 'ZIP archive', 'archive', [_magic(0, b'PK\x03\x04'), _magic(0, b'PK\x05\x06'), _magic(0, b'PK\x07\x08')],
            [_field('flags', 6, 'u16le', 'Local-entry flags'), _field('compression', 8, 'u16le', 'Local compression method'), _field('name_bytes', 26, 'u16le', 'Local filename byte length')],
            endian='little', limitations=['First local entry or empty-archive header only; no EOCD search, ZIP64, CRC, extraction or member safety validation.'], provenance=['https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT']),
        _definition('png', 'PNG image', 'image', [_magic(0,b'\x89PNG\r\n\x1a\n')],
            [_field('ihdr_bytes',8,'u32be','Must be13'), _field('width',16,'u32be','IHDR width'), _field('height',20,'u32be','IHDR height'),
             _field('bit_depth',24,'u8','Per-sample bit depth'), _field('color_type',25,'u8','PNG color model')], endian='big',
            limitations=['IHDR only; no CRC, image data, palette or complete chunk validation.'], provenance=['https://www.w3.org/TR/png-3/']),
        _definition('gif', 'GIF image', 'image', [_magic(0,b'GIF87a'),_magic(0,b'GIF89a')],
            [_field('width',6,'u16le','Logical screen width'),_field('height',8,'u16le','Logical screen height'),_field('packed',10,'u8','Global color-table flag and size')], endian='little',
            limitations=['Logical screen and global-table extent only; no image/frame/LZW/animation validation.'], provenance=['https://www.w3.org/Graphics/GIF/spec-gif89a.txt']),
        _definition('bmp', 'BMP image', 'image', [_magic(0,b'BM')],
            [_field('file_bytes',2,'u32le','Declared file bytes'),_field('pixel_offset',10,'u32le','Pixel data start'),_field('dib_bytes',14,'u32le','DIB header variant'),
             _field('width','DIB+4','u16le/core or i32le/info','Width'),_field('height','DIB+6/core or DIB+8/info','u16le/core or i32le/info','Height; negative INFO height is top-down')], endian='little',
            limitations=['Supported CORE/INFO header variants only; no palette, compression or pixel validation.'], provenance=['https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-storage']),
        _definition('jpeg', 'JPEG image', 'image', [_magic(0,b'\xff\xd8')],
            [_field('segment_bytes','marker+2','u16be','Length includes length field'),_field('geometry','SOF payload','precision/u16be height/u16be width','Bounded marker walk only')], endian='big',
            limitations=['At most64KiB of markers; no entropy data or complete JPEG validation.'], provenance=['https://www.w3.org/Graphics/JPEG/itu-t81.pdf']),
    ]
    from .format_media import definitions
    resources = json.loads((Path(__file__).parent/'data'/'intake_resource_profiles.json').read_text())
    from .codec_profiles import definitions as codec_definitions
    return native + media + definitions(_definition, _field, _magic) + codec_definitions(_definition, _field, _magic) + resources


def _module_records():
    modules = [dict(module_id='format-headers', revision=1, api='fdisbull.format_registry.identify_file',
        capabilities=['bounded-header-recognition', 'sampled-identity'], implemented=True,
        limitations=['No complete codec decode or native compatibility claim.']),
        dict(module_id='native-images', revision=1, api='fdisbull.inspection.identify_header',
        capabilities=['architecture', 'native-header-validation', 'image-views'], implemented=True,
        limitations=['64MiB source; individual LE/NE/PE loaders retain their own unsupported cases.']),
        dict(module_id='console-headers', revision=1, api='fdisbull.roms.probe_rom',
        capabilities=['console-header-validation'], implemented=True,
        limitations=['Header claims; no CPU mapping or execution.']),
        dict(module_id='iso-primary', revision=1, api='fdisbull.rom_disc.parse_disc_volume',
        capabilities=['primary-volume-descriptor'], implemented=True,
        limitations=['No filesystem traversal or CD-audio/TOC parsing.'])]
    from importlib.util import find_spec
    if find_spec('PIL') is not None:
        modules.append(dict(module_id='pillow-images',revision=1,api='PIL.Image.open',
            capabilities=['image-reader-api'],implemented=True,dependencies=['Pillow'],
            limitations=['Dependency API available; identification never invokes it. Full decode needs caller-owned budgets and explicit load/verification.']))
    from .media import media_modules
    for item in media_modules()['modules']:
        modules.append(dict(module_id=item['name'], revision=1, api=item['api'], implemented=True,
            capabilities=list(item.get('capabilities', item.get('methods', []))),
            limitations=[item['limits']], dependencies=item.get('dependencies', [])))
    return modules


def _catalog_links(definitions,modules):
    available={module['module_id'] for module in modules}
    for definition in definitions:
        ident=definition['format_id']
        links=['format-headers']
        if definition['category']=='executable':links.append('native-images')
        if definition['category']=='console-media':links.append('console-headers')
        links += {'dos-mz':['mz-envelope'],'riff-avi':['avi-capture'],
            'iso9660':['iso-primary'],'smacker':['smacker'],'flic':['flic'],'bullfrog-flic12':['flic'],
            'fab':['fab'],'pkware-dcl':['pkware-dcl'],'mads-hag':['mads-hag'],'mads-pack':['mads-pack']}.get(ident,[])
        if definition['category']=='image':links.append('pillow-images')
        for module in links:
            if module in available:yield ident,definition['revision'],module,1


def _decoder_role(identifier):
    if identifier in ('fab', 'pkware-dcl'):
        return 'compression-decoder'
    if identifier in ('mads-hag', 'mads-pack'):
        return 'container-reader'
    if identifier in ('mads-sprite', 'mads-tiles', 'mads-depth', 'mads-background',
                      'mads-depth-map', 'mads-mask', 'mads-font', 'mads-dsr', 'mads-animation'):
        return 'media-decoder'
    return {'format-headers':'recognition-only','native-images':'image-loader',
        'console-headers':'recognition-only','iso-primary':'container-reader',
        'pillow-images':'pixel-reader','agi-picture':'pixel-reader',
        'smacker':'media-decoder-and-framer','avi-capture':'video-reader',
        'mz-envelope':'container-reader','agi-v2':'container-reader',
        'gog-inno':'container-reader','flic':'container-reader'}.get(identifier,'recognition-only')


def resource_profile_hints(path, catalog):
    """Filename/consumer hints are candidates, never signature recognition."""
    import fnmatch
    source=Path(path)
    name=source.name.casefold()
    context=str(source.parent).casefold()
    rows=[]
    for record in catalog['formats']:
        hint=record.get('context_hints')
        if not isinstance(hint,dict) or not all(isinstance(record.get(k),str) for k in ('name','category')):continue
        patterns=hint.get('filename_patterns',[])
        markers=hint.get('game_markers',[])
        if not isinstance(patterns,list) or not isinstance(markers,list):continue
        patterns=[p for p in patterns[:64] if isinstance(p,str) and len(p)<=128]
        markers=[m for m in markers[:32] if isinstance(m,str) and len(m)<=128]
        if not any(fnmatch.fnmatchcase(name,p.casefold()) for p in patterns):continue
        if markers and not any(marker.casefold() in context for marker in markers):continue
        rows.append(dict(format_id=record['format_id'],revision=record['revision'],
            name=record['name'],category=record['category'],qualification='context-candidate-only',
            companions=hint.get('companions',[]),recovery=record.get('limitations',[])))
    return rows


class FormatCatalog:
    """Dedicated metadata-only SQLite catalog; immutable (id,revision) records."""
    def __init__(self, catalog_path=None):
        self.path = None if catalog_path is None else Path(catalog_path).expanduser()
        if self.path is not None:
            if self.path.is_symlink() or not self.path.parent.is_dir() or self.path.exists() and not self.path.is_file():
                raise ValueError('Catalog requires a regular dedicated SQLite file and existing parent')
            if not self.path.exists():
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
        self.db = sqlite3.connect(':memory:' if self.path is None else self.path)
        # SQLite must refuse oversized cells before Python ever receives a row.
        # Allow bounded row overhead; stricter document/key budgets are checked
        # numerically inside the same transaction before materialization.
        self.db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,2*MAX_CATALOG_RECORD_BYTES)
        try:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 5")}
            allowed = {'format_catalog_meta', 'format_definitions', 'format_decoder_modules', 'format_decoder_links'}
            if tables - allowed:
                raise ValueError('Catalog path belongs to another database; use a dedicated format catalog')
            if 'format_catalog_meta' in tables:
                versions = self.db.execute('SELECT schema_version FROM format_catalog_meta LIMIT 2').fetchall()
                if versions and versions != [(SCHEMA_VERSION,)]:
                    raise ValueError('Unsupported format catalog schema version')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('BEGIN IMMEDIATE')
            for statement in (
                'CREATE TABLE IF NOT EXISTS format_catalog_meta(schema_version INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS format_definitions(format_id TEXT NOT NULL,revision INTEGER NOT NULL,record_json TEXT NOT NULL,PRIMARY KEY(format_id,revision))',
                'CREATE TABLE IF NOT EXISTS format_decoder_modules(module_id TEXT NOT NULL,revision INTEGER NOT NULL,record_json TEXT NOT NULL,PRIMARY KEY(module_id,revision))',
                'CREATE TABLE IF NOT EXISTS format_decoder_links(format_id TEXT NOT NULL,format_revision INTEGER NOT NULL,module_id TEXT NOT NULL,module_revision INTEGER NOT NULL,PRIMARY KEY(format_id,format_revision,module_id,module_revision),FOREIGN KEY(format_id,format_revision) REFERENCES format_definitions(format_id,revision),FOREIGN KEY(module_id,module_revision) REFERENCES format_decoder_modules(module_id,revision))',
            ):self.db.execute(statement)
            versions = self.db.execute('SELECT schema_version FROM format_catalog_meta LIMIT 2').fetchall()
            if not versions:
                self.db.execute('INSERT INTO format_catalog_meta VALUES (?)', (SCHEMA_VERSION,))
            elif versions != [(SCHEMA_VERSION,)]:
                raise ValueError('Unsupported format catalog schema version')
            with self.db:
                self._preflight()
                definitions = _builtins()
                modules = _module_records()
                for table, key, records in (('format_definitions', 'format_id', definitions), ('format_decoder_modules', 'module_id', modules)):
                    for record in records:
                        encoded = _json(record)
                        row = self.db.execute(f'SELECT record_json FROM {table} WHERE {key}=? AND revision=?', (record[key], record['revision'])).fetchone()
                        if row is not None and row[0] != encoded:
                            raise ValueError('Conflicting immutable catalog record: ' + record[key])
                        self.db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)', (record[key], record['revision'], encoded))
                for link in _catalog_links(definitions,modules):
                    self.db.execute('INSERT OR IGNORE INTO format_decoder_links VALUES (?,?,?,?)',link)
                self._preflight()
        except sqlite3.DataError as error:
            self.db.close()
            raise ValueError('Format catalog metadata budget exceeded') from error
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _preflight(self):
        """Read bounded scalar counts/sizes before selecting JSON or key text."""
        count=total=0
        for table,key in (('format_definitions','format_id'),('format_decoder_modules','module_id')):
            row=self.db.execute(f'''SELECT COUNT(*),COALESCE(SUM(n),0),COALESCE(MAX(n),0),COALESCE(SUM(bad),0)
                FROM (SELECT length(CAST({key} AS BLOB))+length(CAST(record_json AS BLOB)) AS n,
                             (typeof({key})!='text' OR length({key})=0 OR typeof(record_json)!='text'
                              OR typeof(revision)!='integer' OR revision<1) AS bad
                      FROM {table} LIMIT ?)''',(MAX_CATALOG_RECORDS+1,)).fetchone()
            count+=row[0];total+=row[1]
            if row[3]:raise ValueError('Format catalog requires text records and positive integer revisions')
            if count>MAX_CATALOG_RECORDS or total>MAX_CATALOG_BYTES or row[2]>MAX_CATALOG_RECORD_BYTES:
                raise ValueError('Format catalog metadata budget exceeded')
        links=self.db.execute('''SELECT COUNT(*),COALESCE(SUM(n),0),COALESCE(MAX(n),0),COALESCE(SUM(bad),0)
            FROM (SELECT length(CAST(format_id AS BLOB))+length(CAST(module_id AS BLOB)) AS n,
                         (typeof(format_id)!='text' OR length(format_id)=0 OR typeof(module_id)!='text' OR length(module_id)=0
                          OR typeof(format_revision)!='integer' OR format_revision<1
                          OR typeof(module_revision)!='integer' OR module_revision<1) AS bad
                  FROM format_decoder_links LIMIT ?)''',(MAX_CATALOG_LINKS+1,)).fetchone()
        if links[3]:raise ValueError('Format catalog link revisions must be positive integers and identifiers must be text')
        if links[0]>MAX_CATALOG_LINKS or links[1]>MAX_CATALOG_BYTES or links[2]>MAX_CATALOG_RECORD_BYTES:
            raise ValueError('Format catalog link budget exceeded')

    def snapshot(self):
        def records(table):
            key='format_id' if table=='format_definitions' else 'module_id'
            values=[]
            for identifier,revision,encoded in self.db.execute(f'SELECT {key},revision,record_json FROM {table} ORDER BY 1,2 LIMIT ?',(MAX_CATALOG_RECORDS+1,)):
                if not isinstance(encoded,str):
                    raise ValueError('Catalog records must contain JSON text')
                value=json.loads(encoded)
                if (not isinstance(value,dict) or not isinstance(identifier,str) or
                        type(revision) is not int or revision<1 or value.get(key)!=identifier or value.get('revision')!=revision):
                    raise ValueError('Catalog records require matching identifier and revision metadata')
                values.append(value)
            return values
        self.db.execute('SAVEPOINT format_catalog_snapshot')
        try:
            self._preflight()
            formats=records('format_definitions')
            modules=records('format_decoder_modules')
            links=list(self.db.execute('SELECT format_id,format_revision,module_id,module_revision FROM format_decoder_links ORDER BY 1,2,3,4 LIMIT ?',(MAX_CATALOG_LINKS+1,)))
            shipped_formats=_builtins();shipped_modules=_module_records()
            definitions={(r['format_id'],r['revision']):r for r in shipped_formats}
            shipped={(r['module_id'],r['revision']):r for r in shipped_modules}
            exact_records=all(definitions.get((r['format_id'],r['revision']))==r for r in formats)
            exact_records=exact_records and all(shipped.get((r['module_id'],r['revision']))==r for r in modules)
            exact_records=exact_records and set(links)<=set(_catalog_links(shipped_formats,shipped_modules))
            for module in modules:
                verified=shipped.get((module['module_id'],module['revision']))==module
                module['binding_verified']=verified
                module['decoder_role']=_decoder_role(module['module_id']) if verified else 'unverified'
                if not verified:
                    module['declared_implemented']=module.get('implemented')
                    module['implemented']=False
            result=dict(format='fdisbull-format-modules-1',schema_version=SCHEMA_VERSION,
                catalog_path=str(self.path) if self.path else None,formats=formats,modules=modules,
                bindings=[dict(format_id=a,format_revision=b,module_id=c,module_revision=d) for a,b,c,d in links],
                input_executed=False,contains_file_payloads=False if exact_records else None,
                catalog_content_qualification='exact-shipped-records' if exact_records else 'custom-record-content-unverified',
                inspected_source_bytes_persisted=False,dynamic_plugins_loaded=False)
            self.db.execute('RELEASE format_catalog_snapshot')
            return result
        except BaseException as error:
            self.db.execute('ROLLBACK TO format_catalog_snapshot')
            self.db.execute('RELEASE format_catalog_snapshot')
            if isinstance(error,sqlite3.DataError):
                raise ValueError('Format catalog metadata budget exceeded') from error
            raise


def format_catalog(*, catalog_path=None):
    catalog = FormatCatalog(catalog_path)
    try:
        return catalog.snapshot()
    finally:
        catalog.close()


class ReadBudgetExceeded(ValueError):
    """An admission refusal before another source read, retaining consumed work."""
    def __init__(self, bytes_read, sampled_regions):
        super().__init__('File identification read budget exceeded')
        self.bytes_read = bytes_read
        self.sampled_regions = list(sampled_regions)


class _Reader:
    def __init__(self, stream, size, max_read_bytes=MAX_IDENTIFY_READ_BYTES):
        self.stream, self.size, self.regions = stream, size, []
        self.bytes_read = 0
        self.max_read_bytes = max_read_bytes

    def read(self, offset, count):
        if offset < 0 or count < 0 or count > MAX_BINARY_BYTES:
            raise ValueError('Invalid bounded read')
        amount = min(count, max(0, self.size-offset))
        if self.bytes_read + amount > self.max_read_bytes:
            raise ReadBudgetExceeded(self.bytes_read, self.regions)
        self.stream.seek(offset)
        value = self.stream.read(amount)
        self.bytes_read += len(value)
        self.regions.append(dict(file_offset=offset, size=len(value), sha256=hashlib.sha256(value).hexdigest()))
        return value


def _result(identifier, name, category, *, valid=True, metadata=None, warnings=()):
    return dict(format_id=identifier, name=name, category=category,
        status='recognized-header' if valid else 'recognized-invalid', recognized=True,
        header_valid=valid, metadata=metadata or {}, warnings=list(warnings),
        validation_scope='bounded header facts and explicitly reported table/extent checks; no complete codec validation',
        full_decode=False, native_runtime_tested=False)


def _smacker(prefix, reader):
    if prefix[:4] not in (b'SMK2', b'SMK4'): return None
    if len(prefix) < 104:
        return _result('smacker', prefix[:4].decode(), 'video', valid=False, warnings=['Truncated104-byte Smacker header'])
    width,height,frames,rate,flags = struct.unpack_from('<IIIiI', prefix, 4)
    tree_bytes = struct.unpack_from('<I', prefix, 52)[0]
    physical = frames + (flags & 1)
    issues = []
    if not 0 < width <= 32768 or not 0 < height <= 32768 or not 0 < frames <= 0xffffff or rate == -2147483648:
        issues.append('Invalid dimensions, frame count or rate')
    tree_start = 104 + physical*5
    if tree_start + tree_bytes > reader.size: issues.append('Frame tables or Huffman bytes exceed file')
    meta = dict(version=prefix[:4].decode(), width=width, height=height, logical_frames=frames,
        physical_frames=physical, rate_field=rate, flags=flags, huffman_bytes=tree_bytes,
        header_bytes=104, frame_size_table_offset=104, frame_type_table_offset=104+4*physical,
        huffman_offset=tree_start, audio_tracks=[])
    for index, word in enumerate(struct.unpack_from('<7I', prefix, 72)):
        if word & 0xffffff: meta['audio_tracks'].append(dict(index=index, rate=word & 0xffffff, flags=word >> 24))
    if physical and physical*4 <= MAX_TABLE_BYTES and tree_start <= reader.size:
        sizes = reader.read(104, 4*physical)
        if len(sizes) == 4*physical:
            payload = sum(n[0] & ~3 for n in struct.iter_unpack('<I', sizes))
            meta.update(frame_size_table_checked=True, declared_frame_payload_bytes=payload)
            if tree_start+tree_bytes+payload > reader.size: issues.append('Declared frame payloads exceed file')
    else: meta['frame_size_table_checked'] = False
    warnings = issues + (['SMK4 recognition does not enable the restricted SMK2 framing writer'] if prefix[:4] == b'SMK4' else [])
    if rate==0:
        warnings.append('Zero rate field: playback timing is decoder-specific and is not qualified by header recognition')
    return _result('smacker', meta['version'], 'video', valid=not issues, metadata=meta, warnings=warnings)


def _media(prefix, reader):
    from .codec_profiles import probe as codec_probe
    identified = codec_probe(prefix, reader.size, _result)
    if identified is not None: return identified
    from .format_media import probe
    extra = probe(prefix, reader)
    if extra is not None: return extra
    smk = _smacker(prefix, reader)
    if smk is not None: return smk
    image = _image(prefix,reader)
    if image is not None: return image
    if prefix[:2] == b'\x67\x92':
        valid = len(prefix) >= 16
        meta = {}
        if valid:
            rate = int.from_bytes(prefix[6:8], 'little')
            kind, length = prefix[8], int.from_bytes(prefix[10:14], 'little')
            meta.update(frame_rate_field=rate, first_chunk_type=kind, first_chunk_bytes=length)
            valid = 0 < rate <= 120 and kind in (0,0x20,0x25,0x80) and 16+length <= reader.size
        return _result('vdx', 'VDX header candidate', 'video', valid=valid, metadata=meta,
            warnings=['VDX chunk semantics/LZSS and enclosing game archives are unsupported'] + ([] if valid else ['Truncated or unsupported VDX header/first chunk']))
    if prefix[:2] == b'\x84\x10' and (len(prefix) < 6 or prefix[2:6] in (b'\xff'*4,b'\0'*4)):
        valid = len(prefix) >= 8
        meta = {}
        if valid:
            marker, rate = struct.unpack_from('<IH', prefix, 2)
            meta.update(size_marker=marker, frame_rate_field=rate)
            valid = rate <= 120 and (rate > 0 or marker == 0)
        return _result('roq', 'RoQ', 'video', valid=valid, metadata=meta, warnings=[] if valid else ['Truncated or unsupported RoQ header'])
    if prefix[4:6] in (b'\x11\xaf', b'\x12\xaf'):
        # Bullfrog's packed legacy header stops at byte12. In that layout the
        # following u32 is a frame length, not Autodesk's depth/flags fields.
        if (len(prefix)>=20 and prefix[4:6]==b'\x12\xaf'
                and int.from_bytes(prefix[:4],'little')==12 and prefix[16:18]==b'\xfa\xf1'):
            size_field,magic,frames,width,height=struct.unpack_from('<I4H',prefix)
            chunk_bytes=struct.unpack_from('<I',prefix,12)[0]
            valid=frames>0 and width>0 and height>0 and 16<=chunk_bytes<=reader.size-12
            return _result('bullfrog-flic12','Bullfrog compact FLIC','animation',valid=valid,
                metadata=dict(header_bytes=12,size_field=size_field,frames=frames,width=width,height=height,
                    depth=None,first_frame_offset=12,first_frame_bytes=chunk_bytes,first_frame_type=0xf1fa,
                    first_frame_subchunks=struct.unpack_from('<H',prefix,18)[0]),
                warnings=['Compact header has no color-depth field; frame/subchunk decoding and complete frame-count validation are unsupported']+
                    ([] if valid else ['Invalid compact FLIC geometry or first-frame extent']))
        valid, meta, warnings = len(prefix) >= 128, {}, []
        if valid:
            declared, magic, frames, width, height, depth = struct.unpack_from('<I5H', prefix)
            meta.update(variant='FLI' if magic==0xaf11 else 'FLC', declared_bytes=declared,
                frames=frames, width=width, height=height, depth=depth)
            valid = declared >= 128 and declared <= reader.size and frames > 0 and width > 0 and height > 0
            if declared != reader.size: warnings.append('Header size differs from file; custom companions/trailer semantics are not established')
        if not valid: warnings.append('Truncated or invalid FLI/FLC header extents')
        return _result('flic', 'FLI/FLC', 'animation', valid=valid, metadata=meta, warnings=warnings)
    if prefix.startswith(b'RIFF'):
        valid = len(prefix) >= 12
        form = prefix[8:12] if valid else b''
        identifier = {b'WAVE':'riff-wave',b'AVI ':'riff-avi'}.get(form,'riff')
        meta = dict(form=form.decode('ascii', errors='replace'))
        if valid:
            declared = int.from_bytes(prefix[4:8], 'little')+8
            meta['declared_segment_bytes'] = declared
            valid = 12 <= declared <= reader.size
        return _result(identifier, 'RIFF '+meta['form'], 'audio' if identifier=='riff-wave' else 'video' if identifier=='riff-avi' else 'container', valid=valid, metadata=meta,
            warnings=[] if valid else ['Truncated or invalid RIFF envelope'])
    if prefix[:4] in (b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'):
        local = prefix[:4] == b'PK\x03\x04'
        empty = prefix[:4] == b'PK\x05\x06'
        minimum = 30 if local else 22 if empty else 16
        valid, meta = reader.size >= minimum and len(prefix) >= minimum, {'header_kind':'local-entry' if local else 'end-directory' if empty else 'data-descriptor'}
        if valid and local:
            flags, compression = struct.unpack_from('<HH', prefix, 6)
            name, extra = struct.unpack_from('<HH', prefix, 26)
            compressed = int.from_bytes(prefix[18:22], 'little')
            meta.update(flags=flags, compression_method=compression, filename_bytes=name, extra_bytes=extra, declared_compressed_bytes=compressed)
            valid = 30+name+extra <= reader.size
            if not flags & 8 and compressed != 0xffffffff: valid = valid and 30+name+extra+compressed <= reader.size
        if valid and empty:
            comment = int.from_bytes(prefix[20:22], 'little');meta['comment_bytes'] = comment
            valid = 22+comment <= reader.size
        return _result('zip', 'ZIP', 'archive', valid=valid, metadata=meta, warnings=[] if valid else ['Truncated or invalid first ZIP envelope'])
    return _mp3(prefix, reader)


def _image(prefix,reader):
    if prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        valid,meta = len(prefix)>=33, {}
        if valid:
            length=struct.unpack_from('>I',prefix,8)[0]
            width,height=struct.unpack_from('>II',prefix,16)
            depth,color=prefix[24:26]
            depths={0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}
            valid=(length==13 and prefix[12:16]==b'IHDR' and 0<width<1<<31 and 0<height<1<<31
                and depth in depths.get(color,()) and prefix[26:28]==b'\0\0' and prefix[28] in (0,1))
            meta=dict(width=width,height=height,bit_depth=depth,color_type=color,crc_checked=False)
        return _result('png','PNG','image',valid=valid,metadata=meta,warnings=[] if valid else ['Truncated or invalid PNG IHDR'])
    if prefix[:6] in (b'GIF87a',b'GIF89a'):
        valid,meta=len(prefix)>=13,{}
        if valid:
            width,height=struct.unpack_from('<HH',prefix,6)
            table=3*(1<<((prefix[10]&7)+1)) if prefix[10]&128 else 0
            valid=width>0 and height>0 and 13+table<=reader.size
            meta=dict(version=prefix[:6].decode(),width=width,height=height,global_palette_bytes=table)
        return _result('gif','GIF','image',valid=valid,metadata=meta,warnings=[] if valid else ['Truncated or invalid GIF logical screen/global palette'])
    if prefix.startswith(b'BM'):
        if len(prefix)<18:return _result('bmp','BMP','image',valid=False,warnings=['Truncated BMP/DIB header'])
        declared=struct.unpack_from('<I',prefix,2)[0];offset,dib=struct.unpack_from('<II',prefix,10)
        meta=dict(declared_bytes=declared,pixel_offset=offset,dib_header_bytes=dib)
        valid=14+dib<=reader.size and offset<=reader.size and (not declared or offset<=declared<=reader.size)
        if dib not in (12,40,52,56,108,124):
            result=_result('bmp','BMP','image',metadata=meta,warnings=['Recognized BMP with unsupported DIB header variant'])
            result.update(status='recognized-unsupported-layout',header_valid=None)
            return result
        valid=valid and len(prefix)>=14+dib and offset>=14+dib
        if valid:
            if dib==12:width,height,planes,depth=struct.unpack_from('<4H',prefix,18)
            else:width,height,planes,depth=struct.unpack_from('<iiHH',prefix,18)
            meta.update(width=width,height=abs(height),top_down=height<0,depth=depth)
            valid=width>0 and height!=0 and height!=-(1<<31) and planes==1 and depth in (1,4,8,16,24,32)
        return _result('bmp','BMP','image',valid=valid,metadata=meta,warnings=[] if valid else ['Truncated or invalid BMP/DIB extents'])
    if prefix.startswith(b'\xff\xd8'):
        position,meta,warnings=2,{},[]
        valid=None
        if len(prefix)<4:valid=False;warnings.append('Truncated JPEG marker header')
        for _ in range(4096):
            if valid is False or position>=min(len(prefix),MAX_TABLE_BYTES):break
            if prefix[position]!=255:valid=False;warnings.append('Invalid JPEG marker boundary');break
            while position<len(prefix) and prefix[position]==255:position+=1
            if position>=len(prefix):break
            marker=prefix[position];position+=1
            if marker in (0xd9,0xda):break
            if marker==1 or 0xd0<=marker<=0xd8:continue
            if position+2>len(prefix):break
            length=struct.unpack_from('>H',prefix,position)[0]
            if length<2 or position+length>reader.size:
                valid=False;warnings.append('JPEG segment exceeds file or has invalid length');break
            if position+length>min(len(prefix),MAX_TABLE_BYTES):break
            if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
                if length<8:valid=False;warnings.append('Truncated JPEG SOF');break
                depth=prefix[position+2];height,width=struct.unpack_from('>HH',prefix,position+3);channels=prefix[position+7]
                meta=dict(width=width,height=height,precision=depth,components=channels,sof_marker=marker)
                valid=width>0 and height>0 and channels>0 and length>=8+3*channels
                break
            position+=length
        result=_result('jpeg','JPEG','image',valid=valid is not False,metadata=meta,warnings=warnings)
        if valid is None:
            result.update(status='recognized-header-limit',header_valid=None)
            result['warnings'].append('Geometry not established within bounded JPEG marker walk; full stream unsupported')
        return result
    return None


def _mpeg_header(data):
    if len(data) < 4: return None
    word = int.from_bytes(data[:4], 'big')
    version, layer, bitrate, rate, pad = (word>>19)&3,(word>>17)&3,(word>>12)&15,(word>>10)&3,(word>>9)&1
    if word & 0xffe00000 != 0xffe00000 or version==1 or layer!=1 or bitrate in (0,15) or rate==3: return None
    rates = (44100,48000,32000)
    hz = rates[rate] // (1 if version==3 else 2 if version==2 else 4)
    kbps = (0,32,40,48,56,64,80,96,112,128,160,192,224,256,320)[bitrate] if version==3 else (0,8,16,24,32,40,48,56,64,80,96,112,128,144,160)[bitrate]
    return dict(version={3:'1',2:'2',0:'2.5'}[version], layer=3, bitrate_kbps=kbps, sample_rate=hz,
                frame_bytes=(144000 if version==3 else 72000)*kbps//hz+pad)


def _mp3(prefix, reader):
    offset, metadata = 0, {}
    if prefix.startswith(b'ID3'):
        valid = len(prefix)>=10 and prefix[3] in (2,3,4) and all(v<128 for v in prefix[6:10])
        if not valid: return _result('id3','ID3v2 metadata','metadata',valid=False,warnings=['Invalid or truncated ID3v2 header'])
        length = 0
        for v in prefix[6:10]: length=(length<<7)|v
        offset = 10+length+(10 if prefix[3]==4 and prefix[5]&0x10 else 0)
        metadata['id3'] = dict(major_version=prefix[3], tag_bytes=length, audio_candidate_offset=offset)
        if offset>reader.size: return _result('id3','ID3v2 metadata','metadata',valid=False,metadata=metadata,warnings=['Declared ID3v2 tag exceeds file'])
    first = _mpeg_header(reader.read(offset, 4) if offset else prefix[:4])
    if first is not None:
        second = _mpeg_header(reader.read(offset+first['frame_bytes'],4))
        if second is not None and (first['version'],first['sample_rate'])==(second['version'],second['sample_rate']):
            metadata.update(first_frame=first, second_frame=second, audio_offset=offset)
            return _result('mp3','MPEG Layer III','audio',metadata=metadata)
    if metadata:
        return _result('id3','ID3v2 metadata','metadata',metadata=metadata,warnings=['ID3 tag recognized; two consistent MPEG LayerIII headers were not established'])
    return None


def _iso(prefix, reader):
    raw = prefix[:12] == _SYNC and len(prefix)>=16 and prefix[15]==1
    sector = 2352 if raw else 2048
    block = reader.read(16*sector, sector)
    user = block[16:2064] if raw else block
    if len(user)<7 or user[1:6]!=b'CD001': return None
    from .rom_disc import parse_disc_volume, parse_sega_disc
    volume = parse_disc_volume(block, sector_size=sector, physical_sectors=reader.size//sector)
    if volume is None:
        return _result('iso9660','ISO9660 descriptor','disc',metadata={'descriptor_type':user[0]},warnings=['Sector16 is not a supported primary descriptor; filesystem validation unsupported'])
    result = _result('iso9660','ISO9660','disc',valid=volume['valid'],metadata=dict(sector_bytes=sector,
        sector_user_offset=16 if raw else 0, primary_descriptor=volume), warnings=volume['warnings'])
    console = parse_sega_disc(prefix, file_size=reader.size)
    if console is not None:
        result['console_header'] = console
        result['architecture'] = {k:console.get(k) for k in ('arch','bits','endian','platform')}
    return result


_BINARY_IDS = {'DOS MZ':'dos-mz','PE':'pe','PE32':'pe','PE32+':'pe','NE':'ne','LE':'le','LX':'lx',
    'ELF':'elf','Mach-O':'macho','Mach-O fat':'macho-fat','AIL':'ail','iNES':'nes-ines','NES 2.0':'nes-ines',
    'SNES ROM':'snes-rom','sega-genesis':'sega-genesis','sega-sms':'sega-sms',
    'Sega CD disc':'sega-disc','Sega Saturn disc':'sega-disc'}
_NATIVE_MAGIC = (b'MZ',b'LE',b'\x7fELF',b'\xce\xfa\xed\xfe',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xce',b'\xfe\xed\xfa\xcf',
    b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf',b'\xbf\xba\xfe\xca')


def _large_native_header(prefix,reader):
    """Architecture fields can be observed without validating a whole image."""
    identifier,name,arch,bits,endian='macho','Mach-O header candidate',None,None,None
    metadata={'complete_binary_read':False}
    if prefix.startswith(b'MZ'):
        identifier,name,arch,bits,endian='dos-mz','DOS MZ','x86',16,'little'
        if len(prefix)>=64:
            count=int.from_bytes(prefix[6:8],'little');reloc=int.from_bytes(prefix[24:26],'little')
            offset=int.from_bytes(prefix[60:64],'little')
            overlap=count and reloc<64 and reloc+count*4>60
            if not overlap and 64<=offset<reader.size-2:
                secondary=prefix[offset:offset+256] if offset+256<=len(prefix) else reader.read(offset,256)
                if secondary[:4]==b'PE\0\0':
                    identifier,name,arch,bits='pe','PE header candidate',None,None
                    if len(secondary)>=26:
                        machine=int.from_bytes(secondary[4:6],'little');magic=int.from_bytes(secondary[24:26],'little')
                        arch={0x14c:'x86',0x8664:'x86',0xaa64:'arm64'}.get(machine,f'machine:{machine:#x}')
                        bits={0x10b:32,0x20b:64}.get(magic)
                        name='PE32+' if bits==64 else 'PE32' if bits==32 else name
                        metadata.update(machine=machine,optional_magic=magic)
                    metadata['secondary_header_offset']=offset
                elif secondary[:2] in (b'NE',b'LE',b'LX'):
                    name=secondary[:2].decode();identifier=name.lower();bits=16 if name=='NE' else 32
                    metadata['secondary_header_offset']=offset
    elif prefix.startswith(b'LE'):
        identifier,name,arch,bits,endian='le','LE','x86',32,'little'
    elif prefix.startswith(b'\x7fELF'):
        identifier,name='elf','ELF'
        if len(prefix)>=20 and prefix[4] in (1,2) and prefix[5] in (1,2):
            bits=32 if prefix[4]==1 else 64;endian='little' if prefix[5]==1 else 'big'
            machine=int.from_bytes(prefix[18:20],endian)
            arch={3:'x86',62:'x86',183:'arm64',40:'arm'}.get(machine,f'machine:{machine}')
            metadata['machine']=machine
    elif len(prefix)>=8:
        magic=prefix[:4]
        thin={b'\xce\xfa\xed\xfe':(32,'little'),b'\xcf\xfa\xed\xfe':(64,'little'),b'\xfe\xed\xfa\xce':(32,'big'),b'\xfe\xed\xfa\xcf':(64,'big')}
        if magic in thin:
            bits,endian=thin[magic];cpu=int.from_bytes(prefix[4:8],endian)
            arch={7:'x86',0x1000007:'x86',0x100000c:'arm64',12:'arm'}.get(cpu,f'cpu:{cpu:#x}')
            metadata['cpu_type']=cpu
        else:
            identifier,name='macho-fat','Universal Mach-O header candidate'
            endian='big' if magic in (b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf') else 'little'
            metadata['declared_slice_count']=int.from_bytes(prefix[4:8],endian)
    result=_result(identifier,name,'executable',metadata=metadata,
        warnings=['Source exceeds full binary-reader budget; only signature/architecture fields are observed and image views are not validated'])
    result.update(header_valid=None,status='recognized-unsupported-size',architecture=dict(arch=arch,bits=bits,endian=endian,platform=None))
    return result


def _native(prefix, reader, max_binary_bytes):
    native = prefix.startswith(_NATIVE_MAGIC)
    from .ail import ail_signature
    from .roms import probe_rom
    candidate = None if native else probe_rom(prefix)
    if not native and candidate is None and not ail_signature(prefix): return None, None
    if reader.size>max_binary_bytes:
        if candidate is not None:
            result = _result(_BINARY_IDS.get(candidate['format'],'sega-disc'),candidate['format'],'console-media',metadata={'bounded_probe':candidate},warnings=['Source exceeds full-reader budget; prefix candidate is not full-file validation'])
            result['header_valid'] = None
            result['architecture'] = {k:candidate.get(k) for k in ('arch','bits','endian','platform')}
            return result,None
        return _large_native_header(prefix,reader),None
    data = prefix if len(prefix)==reader.size else reader.read(0,reader.size)
    from .inspection import identify_header
    header = identify_header(data)
    if header['format']=='unknown': return None,data
    identifier = _BINARY_IDS.get(header['format'])
    if identifier is None: return None,data
    result = _result(identifier,header['format'],'console-media' if header.get('family','').startswith('console') else 'executable',
        valid=header['valid'],metadata={'header':header},warnings=header.get('warnings',[]))
    result['architecture'] = {k:header.get(k) for k in ('arch','bits','endian','platform')}
    if 'image_views' in header: result['image_views'] = header['image_views']
    if header.get('slices') is not None: result['slices'] = header['slices']
    return result,data


def _mz_tail(prefix, total):
    if prefix[:2]!=b'MZ' or len(prefix)<28: return None
    last,pages,relocations,paragraphs = struct.unpack_from('<4H',prefix,2)
    header = paragraphs*16
    end = pages*512-(512-last if last else 0) if pages and last<=511 else None
    if end is None or not 28<=header<end<=total: return None
    fact = dict(dos_header_bytes=header, declared_dos_image_end=end, trailing_bytes=total-end,
        declared_overlay_number=int.from_bytes(prefix[26:28],'little'),
        tail_offset=end if end<total else None, tail_structure='opaque' if end<total else 'absent',
        overlays_recovered=False, qualification='DOS-declared range only; tail is not automatically an overlay directory or disposable padding')
    relocation_offset = int.from_bytes(prefix[24:26],'little')
    overlap = relocations and relocation_offset<64 and relocation_offset+relocations*4>60
    if len(prefix)>=64 and not overlap:
        pointer = int.from_bytes(prefix[60:64],'little')
        if 64<=pointer<len(prefix) and prefix[pointer:pointer+2] in (b'NE',b'LE',b'LX',b'PE'):
            fact['secondary_header_offset'] = pointer
    return fact


def identify_file(path, *, catalog_path=None, max_binary_bytes=MAX_BINARY_BYTES,
                  max_read_bytes=MAX_IDENTIFY_READ_BYTES):
    """Identify one regular file without executing it or persisting source bytes.

    Media/disc reads are bounded samples. Existing native and cartridge readers
    receive complete bytes only within the caller's <=64MiB binary-read budget.
    Symlinked sources are accepted through their regular descriptor; samples bind
    observations to the opened bytes, and a final stat check detects mutations.
    """
    if type(max_binary_bytes) is not int or not 1<=max_binary_bytes<=MAX_BINARY_BYTES:
        raise ValueError('max_binary_bytes must be 1..67108864')
    if type(max_read_bytes) is not int or not 0<=max_read_bytes<=MAX_IDENTIFY_READ_BYTES:
        raise ValueError('max_read_bytes exceeds the bounded identification range')
    source = Path(path).expanduser()
    _check_source_catalog(source, catalog_path)
    catalog = format_catalog(catalog_path=catalog_path)
    return _identify_file_with_catalog(source, catalog, max_binary_bytes=max_binary_bytes,
                                       max_read_bytes=max_read_bytes)


def _check_source_catalog(source, catalog_path):
    if catalog_path is not None:
        catalog = Path(catalog_path).expanduser()
        if catalog.resolve()==source.resolve() or catalog.exists() and source.exists() and os.path.samefile(source,catalog):
            raise ValueError('Source and catalog must be different files')


def _identify_file_with_catalog(path, catalog, *, max_binary_bytes=MAX_BINARY_BYTES,
                                max_read_bytes=MAX_IDENTIFY_READ_BYTES):
    """One bounded probe with a pre-qualified catalog snapshot for batch reuse."""
    if type(max_binary_bytes) is not int or not 1<=max_binary_bytes<=MAX_BINARY_BYTES:
        raise ValueError('max_binary_bytes must be 1..67108864')
    if type(max_read_bytes) is not int or not 0<=max_read_bytes<=MAX_IDENTIFY_READ_BYTES:
        raise ValueError('max_read_bytes exceeds the bounded identification range')
    source = Path(path).expanduser()
    _check_source_catalog(source, catalog.get('catalog_path'))
    reader = None
    try:
        fd = os.open(source, os.O_RDONLY | getattr(os,'O_NONBLOCK',0))
        with os.fdopen(fd,'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode): raise ValueError('Identification requires a regular file')
            reader = _Reader(stream,before.st_size,max_read_bytes)
            prefix = reader.read(0,min(PREFIX_BYTES,before.st_size))
            result = _media(prefix,reader)
            complete = prefix if len(prefix)==before.st_size else None
            if result is None: result = _iso(prefix,reader)
            if result is None:
                result,data = _native(prefix,reader,max_binary_bytes)
                if data is not None: complete=data
            if result is None:
                result = dict(format_id=None,name='unknown',category='unknown',status='unknown',recognized=False,
                    header_valid=None,metadata={},architecture=None,warnings=['No supported header established; filename extensions are not evidence. Signatureless COM requires explicit caller selection.'],
                    validation_scope='bounded signature/header probes only',full_decode=False,native_runtime_tested=False)
            tail = _mz_tail(prefix,before.st_size)
            if tail is not None: result['mz_envelope']=tail
            after = os.fstat(stream.fileno())
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ValueError('Source changed during identification')
    except BaseException as error:
        error.bytes_read = reader.bytes_read if reader is not None else 0
        error.sampled_regions = list(reader.regions) if reader is not None else []
        raise
    identifier = result['format_id']
    links = [b for b in catalog['bindings'] if b['format_id']==identifier and b['format_revision']==1]
    modules = {(m['module_id'],m['revision']):m for m in catalog['modules']}
    result['decoder_modules'] = [modules[(b['module_id'],b['module_revision'])] for b in links]
    result.setdefault('architecture',None)
    return dict(format='fdisbull-file-identification-1',source=dict(path=str(source),size=before.st_size,
        sha256=hashlib.sha256(complete).hexdigest() if complete is not None else None,
        hash_scope='whole opened file' if complete is not None else 'sampled regions only; whole-file identity not established',
        sampled_regions=reader.regions, bytes_read=reader.bytes_read,
        opened_identity=dict(device=before.st_dev,inode=before.st_ino,mtime_ns=before.st_mtime_ns,ctime_ns=before.st_ctime_ns)), identification=result,
        catalog=dict(schema_version=SCHEMA_VERSION,path=catalog['catalog_path'],definition_revision=1 if identifier else None,
            contains_file_payloads=catalog['contains_file_payloads'],content_qualification=catalog['catalog_content_qualification']),
        input_executed=False, source_bytes_persisted=False,inspected_source_bytes_persisted=False)
