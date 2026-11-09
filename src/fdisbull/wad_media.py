"""Private classic Doom WAD asset inventory and lossless-plus-decoded export.

One format adapter serves IWADs/PWADs, with optional base-WAD resolution.
No title-specific offsets, executable launch, inferred gameplay, or font files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import struct

from .wad_archive import WadArchive, Lump, MAX_SOURCE
from . import wad_codecs as codec

DEFAULT_OUTPUT = 256 * 1024 * 1024
MAX_OUTPUT = 512 * 1024 * 1024
MAX_WORK_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 64 * 1024 * 1024
MAX_FILES = 50_000
SPEC = 'references/wad-media.md'
_MARKER = re.compile(r'^(F|FF|F[0-9]|S|SS|S[0-9]|P|PP|P[0-9])_(START|END)$')
_MAP = re.compile(r'^(E[0-9]M[0-9]|MAP[0-9]{2})$')
_MAP_ORDER = ('THINGS', 'LINEDEFS', 'SIDEDEFS', 'VERTEXES', 'SEGS', 'SSECTORS', 'NODES', 'SECTORS', 'REJECT', 'BLOCKMAP')


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8')


def _identity(data: bytes) -> dict:
    return dict(size=len(data), sha256=sha256(data).hexdigest())


def _stem(lump: Lump) -> str:
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', lump.name)[:32] or 'unnamed'
    return f'{lump.index:06d}_{safe}'


@dataclass
class Context:
    primary: WadArchive
    base: WadArchive | None
    lookup: dict
    roles: list[dict]
    issues: list[dict]
    palettes: tuple[bytes, ...]
    palette_source: dict | None
    pnames: list[str] | None
    pnames_source: dict | None


def _load(path, base_wad=None) -> Context:
    from .media import _snapshot
    primary = WadArchive.parse(_snapshot(path, MAX_SOURCE), max_lumps=20_000)
    base = WadArchive.parse(_snapshot(base_wad, MAX_SOURCE), max_lumps=20_000) if base_wad is not None else None
    lookup, roles, issues = {}, [], []
    total = 0
    for role, archive in [('base', base), ('primary', primary)]:
        if archive is None:
            continue
        roles.append(dict(role=role, kind=archive.kind, **_identity(archive.data)))
        for lump in archive.lumps:
            total += lump.size
            if total > MAX_WORK_BYTES:
                raise ValueError('WAD repeated-payload work budget exceeded')
            lookup[lump.key] = (role, archive, lump)
    palettes, palette_source, pnames, pnames_source = (), None, None, None
    for key, parser in [(b'PLAYPAL', codec.decode_palettes), (b'PNAMES', codec.decode_pnames)]:
        entry = lookup.get(key)
        if entry is None:
            continue
        role, archive, lump = entry
        source = dict(input_role=role, **lump.summary(archive.data))
        try:
            decoded = parser(lump.payload(archive.data))
            if key == b'PLAYPAL':
                palettes, palette_source = decoded, source
            else:
                pnames, pnames_source = decoded, source
        except codec.WadDecodeError as error:
            issues.append(dict(source=source, reason=str(error)))
    return Context(primary, base, lookup, roles, issues, palettes, palette_source, pnames, pnames_source)


def _classify(context: Context) -> list[dict]:
    archive = context.primary
    namespace = set()
    map_indices = {}
    map_profiles = {}
    for i, row in enumerate(archive.lumps):
        if _MAP.fullmatch(row.name) and i + 1 < len(archive.lumps) and archive.lumps[i + 1].name == 'TEXTMAP':
            map_indices[i] = row.name
            map_profiles[i] = 'udmf'
            for j in range(i + 1, len(archive.lumps)):
                if _MAP.fullmatch(archive.lumps[j].name):
                    break
                map_indices[j] = row.name
                if archive.lumps[j].name == 'ENDMAP':
                    break
        if _MAP.fullmatch(row.name) and tuple(x.name for x in archive.lumps[i + 1:i + 11]) == _MAP_ORDER:
            map_indices[i] = row.name
            extended = i + 11 < len(archive.lumps) and archive.lumps[i + 11].name == 'BEHAVIOR'
            map_profiles[i] = 'hexen' if extended else 'classic'
            if extended:
                map_indices[i + 11] = row.name
            for j in range(i + 1, i + 11):
                map_indices[j] = row.name
    records = []
    for lump in archive.lumps:
        name, data = lump.name.upper(), lump.payload(archive.data)
        item = dict(id=f'lump:{lump.index}', **lump.summary(archive.data))
        item['name_bytes_hex'] = lump.name_bytes.hex()
        marker = _MARKER.fullmatch(name)
        if marker:
            token, operation = marker.groups()
            if operation == 'START':
                namespace.add(token)
            else:
                namespace.discard(token)
            item.update(kind='namespace-marker', namespace=token)
        elif lump.index in map_indices:
            item.update(kind='map-marker' if _MAP.fullmatch(name) else 'map-data', map=map_indices[lump.index])
            if lump.index in map_profiles:
                item['map_profile'] = map_profiles[lump.index]
        elif not data:
            item.update(kind='empty')
        elif name == 'PLAYPAL':
            item.update(kind='palette')
        elif name == 'COLORMAP':
            item.update(kind='colormap')
        elif name == 'PNAMES':
            item.update(kind='patch-names')
        elif name in ('TEXTURE1', 'TEXTURE2'):
            item.update(kind='texture-definitions', effective=context.lookup.get(lump.key, (None, None, None))[-1] is lump)
        elif name in ('DMXGUS', 'DMXGUSC'):
            item.update(kind='gus-config')
        elif name == 'GENMIDI':
            item.update(kind='opl-instruments')
        elif name == 'ENDOOM':
            item.update(kind='text-screen')
        elif data.startswith(b'MUS\x1a'):
            item.update(kind='mus')
        elif data.startswith(b'MThd'):
            item.update(kind='midi')
        elif name.startswith('DS') and data[:2] == b'\x03\x00':
            item.update(kind='dmx-pcm')
        elif name.startswith('DP') and data[:2] == b'\0\0':
            item.update(kind='pc-speaker')
        elif any(x.startswith('F') for x in namespace):
            item.update(kind='flat', namespace='flats')
        elif any(x.startswith('S') for x in namespace):
            item.update(kind='patch', namespace='sprites')
        elif any(x.startswith('P') for x in namespace):
            item.update(kind='patch', namespace='patches')
        elif name.startswith('DEMO'):
            item.update(kind='opaque', reason='recorded gameplay input is retained, not interpreted as media')
        else:
            try:
                details, _ = codec.patch_posts(data)
                item.update(kind='patch', namespace='graphics', detection='validated classic patch layout', image=details)
            except codec.WadDecodeError:
                item.update(kind='opaque', reason='no supported media interpretation; raw bytes retained')
        records.append(item)
    return records


def _summary(context: Context, records: list[dict]) -> dict:
    archive = context.primary
    return dict(format='fdisbull-wad-media-1', adapter='doom-wad', adapter_version=1,
                specification=SPEC, inputs=context.roles, source=_identity(archive.data),
                kind=archive.kind, lump_count=len(records), counts=dict(sorted(Counter(x['kind'] for x in records).items())),
                duplicate_names={n: c for n, c in sorted(Counter(x.name for x in archive.lumps).items()) if c > 1},
                palette_count=len(context.palettes), palette_source=context.palette_source,
                pnames_source=context.pnames_source, dependency_issues=context.issues,
                input_executed=False, qualification='format decoding, not runtime rendering or gameplay equivalence',
                lookup_policy='last case-insensitive lump name wins, primary overrides optional base; directory occurrences retained',
                next_steps=['Use --member all for complete raw-plus-decoded extraction.',
                            'Sprites expose frames/rotations only; animation timing and actor logic require executable evidence.',
                            'MUS converts to event/MIDI data; original music timbre needs a separately qualified synthesizer.'])


def inspect_wad_media(path, *, base_wad=None, start: int = 0, limit: int = 40) -> dict:
    if type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('invalid WAD inventory pagination')
    context = _load(path, base_wad)
    records = _classify(context)
    end = min(start + limit, len(records))
    return dict(_summary(context, records), members=records[start:end], start=start,
                next_start=end if end < len(records) else None)


class _Sink:
    def __init__(self, root: Path, limit: int):
        self.root, self.limit, self.bytes = root, limit, 0
        self.files: list[dict] = []
        self.pixels = 0

    def write(self, relative: str, data: bytes) -> dict:
        # All relative names are generated internally, never accepted from a lump.
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute() or any(p in ('..', '.') for p in parts):
            raise ValueError('unsafe generated output path')
        if self.bytes + len(data) > self.limit or len(self.files) >= MAX_FILES:
            raise ValueError('WAD output byte/file budget exceeded')
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('xb') as out:
            os.chmod(out.fileno(), 0o600)
            out.write(data)
        record = dict(path=relative, **_identity(data))
        self.files.append(record)
        self.bytes += len(data)
        return record

    def json(self, relative: str, value: object) -> dict:
        return self.write(relative, _json(value))

    def admit_pixels(self, width: int, height: int) -> None:
        self.pixels += width * height
        if self.pixels > MAX_PIXELS:
            raise ValueError('WAD aggregate decoded-pixel budget exceeded')


def _raster_outputs(sink: _Sink, stem: str, image: codec.Raster, palette: bytes | None, palette_source: dict | None) -> list[dict]:
    # Exact indices and opacity survive PNG conversion and alternate palettes.
    outputs = [sink.write(stem + '.indices.bin', image.indices), sink.write(stem + '.opacity.bin', image.opacity)]
    if palette is not None:
        outputs.append(sink.write(stem + '.png', image.png(palette)))
    return outputs


def _sprites(records: list[dict]) -> list[dict]:
    frames = []
    for item in records:
        if item.get('namespace') != 'sprites' or item['kind'] != 'patch':
            continue
        name = item['name'].upper()
        if len(name) not in (6, 8):
            continue
        views = []
        for pos in (4, 6) if len(name) == 8 else (4,):
            frame, rotation = name[pos], name[pos + 1]
            if 0 <= ord(frame) - ord('A') < 29 and rotation in '012345678':
                views.append(dict(frame=frame, frame_index=ord(frame) - ord('A'), rotation=int(rotation), mirrored=pos == 6))
        if views:
            frames.append(dict(lump=item['id'], sprite=name[:4], views=views,
                               timing=None, state_transition=None,
                               qualification='name-convention mapping, not animation or actor semantics'))
    return frames


def _map_export(archive: WadArchive, marker: Lump) -> dict:
    """Exact fixed-record projections; raw REJECT/BLOCKMAP remain attached."""
    from .structure_wad import inspect_wad
    # A bounded one-map WAD avoids repeatedly walking all maps for each export.
    selected = archive.lumps[marker.index:marker.index + 11]
    body, directory = bytearray(), bytearray()
    for row in selected:
        content = row.payload(archive.data)
        directory += struct.pack('<ii8s', 12 + len(body), len(content), row.name_bytes)
        body += content
    packed = b'PWAD' + struct.pack('<ii', len(selected), 12 + len(body)) + body + directory
    checked = inspect_wad(bytes(packed))
    if not checked or not checked['maps']:
        raise codec.WadDecodeError('map layout unavailable: ' + str(checked.get('unresolved') if checked else 'not WAD'))
    draft = checked['maps'][0]
    # Replace temporary coordinates with real source provenance; no fabricated pin.
    tables = {}
    formats = {'THINGS': '<hhHHH', 'LINEDEFS': '<7H', 'SIDEDEFS': '<hh8s8s8sH',
               'VERTEXES': '<hh', 'SEGS': '<6H', 'SSECTORS': '<2H',
               'NODES': '<12h2H', 'SECTORS': '<hh8s8shHH'}
    fields = {'THINGS': ['x', 'y', 'angle', 'type', 'flags'],
              'LINEDEFS': ['v1', 'v2', 'flags', 'special', 'tag', 'front', 'back'],
              'SIDEDEFS': ['x_offset', 'y_offset', 'upper_texture', 'lower_texture', 'middle_texture', 'sector'],
              'VERTEXES': ['x', 'y'], 'SEGS': ['v1', 'v2', 'angle_raw', 'linedef', 'side', 'offset_raw'],
              'SSECTORS': ['count', 'first_seg'],
              'NODES': ['x', 'y', 'dx', 'dy', 'r_top', 'r_bottom', 'r_left', 'r_right',
                        'l_top', 'l_bottom', 'l_left', 'l_right', 'right_child_raw', 'left_child_raw'],
              'SECTORS': ['floor_height', 'ceiling_height', 'floor_texture', 'ceiling_texture', 'light', 'special', 'tag']}
    for row in selected[1:]:
        table = dict(source=row.summary(archive.data), raw_path=f'raw/{_stem(row)}.lmp')
        if row.name in formats:
            table['fields'] = fields[row.name]
            table['records'] = [[codec.wad_name(v) if isinstance(v, bytes) else v for v in values]
                                for values in struct.iter_unpack(formats[row.name], row.payload(archive.data))]
        tables[row.name] = table
    return dict(format='classic-wad-map-assets-1', name=marker.name, source_sha256=sha256(archive.data).hexdigest(),
                marker=marker.summary(), tables=tables, bounds=draft['bounds'],
                reference_issues=draft['reference_issues'], unchecked=draft['unchecked'],
                qualification='initial definitions; no active entities, executable events or playable scene')


def _container_ranges(archive: WadArchive, sink: _Sink) -> list[dict]:
    """Preserve header, directory and otherwise unreferenced bytes for exact rebuild."""
    n, d, source = len(archive.lumps), archive.directory_offset, archive.data
    result = [dict(offset=0, **sink.write('container/header.bin', source[:12])),
              dict(offset=d, **sink.write('container/directory.bin', source[d:d + n * 16]))]
    covered = sorted([(0, 12), (d, d + n * 16)] + [(x.offset, x.offset + x.size) for x in archive.lumps if x.size])
    cursor = 0
    gap = 0
    for start, end in covered:
        if start > cursor:
            result.append(dict(offset=cursor, **sink.write(f'container/gap-{gap:06d}.bin', source[cursor:start])))
            gap += 1
        cursor = max(cursor, end)
    if cursor < len(source):
        result.append(dict(offset=cursor, **sink.write(f'container/gap-{gap:06d}.bin', source[cursor:])))
    return result


def extract_wad_media(path, output, *, member: str = 'all', base_wad=None, palette: int = 0,
                      wad_mode: str = 'both', max_output_bytes: int = DEFAULT_OUTPUT) -> dict:
    """Export all/single primary lumps and effective composites into new private dir.

    Source files are snapshotted once. A decode error preserves its raw lump and
    is recorded; unsafe containers, output failures and budgets abort/roll back.
    The optional base only supplies explicitly referenced decode dependencies.
    """
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('WAD output budget must be 1..536870912')
    if wad_mode not in ('raw', 'decoded', 'both') or type(palette) is not int or not 0 <= palette < 256:
        raise ValueError('invalid WAD extraction mode/palette')
    context = _load(path, base_wad)
    records = _classify(context)
    if context.palettes and palette >= len(context.palettes):
        raise ValueError('selected palette is absent')
    selected = records
    if member != 'all':
        if not isinstance(member, str):
            raise ValueError('member must be all, lump:N or name:NAME')
        if member.startswith('name:'):
            selected = [x for x in records if x['name'].casefold() == member[5:].casefold()]
        else:
            selected = [x for x in records if x['id'] == member]
        if len(selected) != 1:
            raise ValueError('missing or ambiguous WAD member; use a directory lump:N identity')
    from .output_artifacts import _private_directory
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if not destination.parent.is_dir():
        raise ValueError('output parent must already exist and be private')
    _private_directory(destination.parent)
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        sink = _Sink(destination, max_output_bytes)
        archive = context.primary
        palette_bytes = context.palettes[palette] if context.palettes else None
        manifest = dict(_summary(context, records), member=member, mode=wad_mode,
                        palette_index=palette, members=[], textures=[], container_ranges=[])
        if member == 'all' and wad_mode in ('raw', 'both'):
            manifest['container_ranges'] = _container_ranges(archive, sink)
        # Cache only decoded dependencies, bounded by pixel budget, not entire bank.
        cache: dict[tuple[str, int], codec.Raster] = {}
        def dependency(name: str) -> tuple[codec.Raster, dict]:
            try:
                entry = context.lookup.get(name.encode('ascii').upper())
            except UnicodeEncodeError:
                entry = None
            if entry is None:
                raise codec.WadDecodeError('missing texture patch: ' + name)
            role, owner, row = entry
            key = role, row.index
            if key not in cache:
                data = row.payload(owner.data)
                details, _ = codec.patch_posts(data)
                sink.admit_pixels(details['width'], details['height'])
                cache[key] = codec.decode_patch(data)
            return cache[key], dict(input_role=role, **row.summary(owner.data))
        for record in selected:
            item = dict(record, outputs=[])
            row = archive.lumps[record['index']]
            data = row.payload(archive.data)
            stem = _stem(row)
            if wad_mode in ('raw', 'both'):
                item['raw'] = sink.write(f'raw/{stem}.lmp', data)
            if wad_mode == 'raw':
                item['status'] = 'raw-only'
                manifest['members'].append(item)
                continue
            try:
                kind = item['kind']
                if kind in ('patch', 'flat'):
                    if kind == 'patch':
                        details, _ = codec.patch_posts(data)
                        sink.admit_pixels(details['width'], details['height'])
                        image = codec.decode_patch(data)
                    else:
                        sink.admit_pixels(64, 64)
                        image = codec.decode_flat(data)
                    item['image'] = dict(width=image.width, height=image.height, left=image.left, top=image.top,
                                         palette_source=context.palette_source, palette_index=palette,
                                         opacity='separate 0/255 plane; no transparent palette index')
                    item['outputs'] += _raster_outputs(sink, f'images/{stem}', image, palette_bytes, context.palette_source)
                    if palette_bytes is None:
                        item['missing'] = 'PLAYPAL absent; index/opacity retained without invented colors'
                elif kind == 'palette':
                    palettes = codec.decode_palettes(data)
                    item['outputs'].append(sink.json(f'tables/{stem}.json', dict(palettes=[list(x) for x in palettes])))
                    for n, pal in enumerate(palettes):
                        grid = codec.Raster(16, 16, bytes(range(256)), b'\xff' * 256)
                        sink.admit_pixels(16, 16)
                        item['outputs'].append(sink.write(f'palettes/{stem}-{n:03d}.png', grid.png(pal)))
                elif kind == 'colormap':
                    item['outputs'].append(sink.json(f'tables/{stem}.json', dict(index_maps=codec.decode_colormaps(data))))
                elif kind == 'patch-names':
                    item['outputs'].append(sink.json(f'tables/{stem}.json', dict(names=codec.decode_pnames(data))))
                elif kind == 'texture-definitions':
                    definitions = codec.decode_textures(data)
                    item['outputs'].append(sink.json(f'textures/{stem}.json', dict(textures=definitions)))
                    if item['effective']:
                        for definition in definitions:
                            entry = dict(definition, source=item['id'], outputs=[], dependencies=[], pnames_source=context.pnames_source)
                            try:
                                if context.pnames is None:
                                    raise codec.WadDecodeError('PNAMES unavailable; cannot bind texture patch indices')
                                patches = []
                                for part in definition['patches']:
                                    index = part['pnames_index']
                                    if index >= len(context.pnames):
                                        raise codec.WadDecodeError('texture PNAMES index outside table')
                                    image, source = dependency(context.pnames[index])
                                    patches.append(image)
                                    entry['dependencies'].append(source)
                                sink.admit_pixels(definition['width'], definition['height'])
                                image = codec.compose_texture(definition, patches)
                                name = re.sub('[^A-Za-z0-9_-]', '_', definition['name']) or 'unnamed'
                                prefix = f'textures/{row.index:06d}-{definition["index"]:05d}_{name}'
                                entry['outputs'] = _raster_outputs(sink, prefix, image, palette_bytes, context.palette_source)
                                entry.update(status='decoded', palette_index=palette, palette_source=context.palette_source,
                                             transparent_pixels=image.opacity.count(0))
                                if palette_bytes is None:
                                    entry['missing'] = 'PLAYPAL absent; index/opacity retained'
                            except codec.WadDecodeError as error:
                                entry.update(status='decode-error', reason=str(error))
                            manifest['textures'].append(entry)
                elif kind == 'dmx-pcm':
                    info, samples = codec.decode_dmx(data)
                    item['audio'] = info
                    item['outputs'].append(sink.write(f'audio/{stem}.wav', codec.pcm_wav(samples, info['sample_rate'])))
                    if info['dmx_playback_slice'] is not None:
                        first, end = info['dmx_playback_slice']
                        item['outputs'].append(sink.write(f'audio/{stem}.dmx-playback.wav', codec.pcm_wav(samples[first:end], info['sample_rate'])))
                elif kind == 'pc-speaker':
                    item['outputs'].append(sink.json(f'audio/{stem}.tones.json', codec.decode_pc_speaker(data)))
                elif kind == 'mus':
                    score = codec.decode_mus(data)
                    item['music'] = dict(events=len(score['events']), total_ticks=score['total_ticks'], tick_rate_hz=140, warnings=score['warnings'])
                    item['outputs'] += [sink.write(f'music/{stem}.mid', codec.mus_midi(score)),
                                        sink.json(f'music/{stem}.events.json', score)]
                elif kind == 'midi':
                    item['music'] = codec.inspect_midi(data)
                    item['outputs'].append(sink.write(f'music/{stem}.mid', data))
                elif kind == 'gus-config':
                    if any(v < 32 and v not in (9, 10, 13) for v in data) or any(v > 126 for v in data):
                        raise codec.WadDecodeError('GUS configuration is not printable ASCII')
                    item['outputs'].append(sink.write(f'audio/{stem}.txt', data))
                    item['note'] = 'GUS patch-name configuration; external instrument sample files are not present here'
                elif kind == 'opl-instruments':
                    item['outputs'].append(sink.json(f'audio/{stem}.instruments.json', codec.decode_genmidi(data)))
                elif kind == 'text-screen':
                    screen = codec.decode_endoom(data)
                    item['outputs'] += [sink.json(f'text/{stem}.json', screen),
                                        sink.write(f'text/{stem}.txt', (screen['text'] + '\n').encode('utf-8'))]
                elif kind == 'map-marker':
                    if item.get('map_profile') != 'classic':
                        raise codec.WadDecodeError('unsupported map profile: ' + item.get('map_profile', 'unknown'))
                    projection = _map_export(archive, row)
                    for table in projection['tables'].values():
                        table['raw_available'] = wad_mode in ('raw', 'both') and member == 'all'
                        if not table['raw_available']:
                            table.pop('raw_path', None)
                    item['outputs'].append(sink.json(f'maps/{stem}.json', projection))
                elif kind == 'map-data':
                    item['status'] = 'map-member'
                elif kind in ('namespace-marker', 'empty'):
                    item['status'] = 'marker'
                else:
                    item['status'] = 'raw-only' if wad_mode == 'both' else 'not-decoded'
                item.setdefault('status', 'decoded')
            except codec.WadDecodeError as error:
                item.update(status='decode-error', reason=str(error))
            manifest['members'].append(item)
        if wad_mode != 'raw':
            sink.json('sprite-views.json', dict(frames=_sprites(selected), timing=None,
                      note='No animation rates or executable state transitions are stored in this export.'))
        failures = [dict(id=r.get('id', r.get('name')), reason=r['reason'])
                    for r in manifest['members'] + manifest['textures'] if r['status'] == 'decode-error']
        missing = [r.get('id', r.get('name')) for r in manifest['members'] + manifest['textures'] if 'missing' in r]
        manifest.update(raw_lumps_extracted=sum('raw' in r for r in manifest['members']),
                        all_primary_lumps_preserved=member == 'all' and wad_mode in ('raw', 'both'),
                        decode_failures=failures, missing_dependencies=missing,
                        decoded_kinds=dict(sorted(Counter(r['kind'] for r in manifest['members'] if r['status'] == 'decoded').items())),
                        files=sink.files.copy(), payload_output_bytes=sink.bytes,
                        decoded_pixel_work=sink.pixels, output_budget=max_output_bytes)
        # The manifest counts towards the same budget. It does not hash itself.
        manifest_file = sink.json('wad-manifest.json', manifest)
        return dict(format='fdisbull-wad-extraction-1', adapter='doom-wad', input_executed=False,
                    output=str(destination), manifest=manifest_file,
                    source=manifest['source'], lump_count=len(records), selected_lumps=len(selected),
                    raw_lumps_extracted=manifest['raw_lumps_extracted'],
                    all_primary_lumps_preserved=manifest['all_primary_lumps_preserved'],
                    decoded_kinds=manifest['decoded_kinds'], composed_textures=sum(r['status'] == 'decoded' for r in manifest['textures']),
                    decode_failures=failures[:20], decode_failure_count=len(failures),
                    missing_dependency_count=len(missing),
                    opaque_lumps=sum(r['kind'] == 'opaque' for r in selected),
                    files_written=len(sink.files), output_bytes=sink.bytes,
                    complete=True, qualification='extraction completed; decode coverage is reported separately')
    except BaseException:
        shutil.rmtree(destination)
        raise
