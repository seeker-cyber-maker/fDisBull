"""Independent media catalog, JSON adapters and CLI; no processor/runtime import."""
from __future__ import annotations

import json
from .mads_resources import HagArchive, MadsPack, snapshot, require, bounded_int
from .mads_media import (identity, decode_sprites, decode_tiles, decode_background,
                         decode_dsr, decode_font, decode_mask, decode_animation)
from .codec_fab import decode_fab
from .codec_dcl import decode_dcl

NAMES = ('fab', 'pkware-dcl', 'mads-hag', 'mads-pack', 'mads-sprite', 'mads-tiles',
         'mads-depth', 'mads-background', 'mads-depth-map', 'mads-mask', 'mads-font',
         'mads-dsr', 'mads-animation')


def catalog():
    variants = (
        'FAB windows 10..13; exact expected_size required',
        'PKWARE DCL coded/uncoded literals, dictionary bits 4..6; not PKZIP method 6',
        'MADSCONCAT 1.0 resource directory; select number to extract',
        'MADSPACK 1.0/2.0 raw, FAB and DCL; select number for decoded section',
        'SS indexed sprite frames with explicit transparency and local palettes',
        'TT picture tiles; number selects one tile',
        'TTn four-bit depth tiles; number selects one tile; no guessed colors',
        'TT plus explicit map_path MM; reconstruct full picture canvas',
        'TTn plus explicit map_path MMn; reconstruct four-bit depth canvas',
        'WW/PP one-bit planes; explicit width and height required',
        'FF two-bit glyphs; number 1..127; caller-selected colors not embedded',
        'DSR FAB unsigned-eight-bit mono PCM and lossless WAV',
        'AA timeline/reference records; no compositor or timed playback')
    return [dict(name=name, layer='compression' if i < 2 else 'resource-container' if i < 4 else 'asset-decoding',
                 api='fdisbull.mads_media_adapters.prepare',
                 methods=['media-inspect', 'media-extract', 'python-module:mads_media_adapters'],
                 dependencies=[], variants=variants[i],
                 limits='Bounded source/expansion; private selected output; no game execution or live palette/host semantics',
                 specification='docs/MADS_MEDIA_RUNTIME.md') for i, name in enumerate(NAMES)]


def _source(path, member, inputs, role):
    if member is None:
        raw = snapshot(path, 128*1024*1024 if role == 'archive' else 64*1024*1024)
        inputs.append(dict(role=role, **identity(raw)))
    else:
        archive = HagArchive.read(path)
        item, raw = archive.select(member)
        inputs.append(dict(role=role+'-archive', **identity(archive.source)))
        inputs.append(dict(role=role, **identity(raw), source_member=item.name,
                           member_index=item.index, file_offset=item.offset))
    return raw


def prepare(path, adapter, *, number=None, source_member=None, map_path=None,
            map_member=None, expected_size=None, width=None, height=None):
    require(type(adapter) is str and adapter in NAMES, 'Unknown independent media adapter')
    allowed_number = {'mads-hag', 'mads-pack', 'mads-sprite', 'mads-tiles', 'mads-depth', 'mads-font', 'mads-dsr'}
    require(number is None or adapter in allowed_number, 'number does not apply to this adapter')
    require(expected_size is None or adapter in ('fab', 'pkware-dcl'), 'expected_size applies only to raw codecs')
    require((width is None and height is None) or adapter == 'mads-mask', 'Geometry applies only to mads-mask')
    require((map_path is None and map_member is None) or adapter in ('mads-background', 'mads-depth-map'),
            'Companion map applies only to background/depth-map')
    require(adapter != 'mads-hag' or source_member is None, 'HAG extraction uses its integer number selector')
    inputs = []
    data = _source(path, source_member, inputs, 'archive' if adapter == 'mads-hag' else 'container')
    payloads, offsets = {}, {}
    image = sample = None
    if adapter in ('fab', 'pkware-dcl'):
        if adapter == 'fab':
            require(expected_size is not None, 'FAB needs expected_size from its owning container')
            decoded, consumed = decode_fab(data, expected_size)
        else:
            decoded, consumed = decode_dcl(data, expected_size)
        details = dict(consumed_bytes=consumed, opaque_tail_bytes=len(data)-consumed)
        payloads['decoded'] = decoded
    elif adapter == 'mads-hag':
        archive = HagArchive.read(data); details = archive.metadata()
        if number is not None:
            entry, payloads['resource'] = archive.select(number)
            offsets['resource'] = entry.offset
            details['selected_index'] = entry.index
    elif adapter == 'mads-pack':
        pack = MadsPack.read(data); details = pack.metadata()
        selected = 0 if number is None else number
        bounded_int(selected, 'section number', 0, len(pack.sections)-1)
        payloads['section'] = pack.sections[selected].data
        details['selected_index'] = selected
    elif adapter in ('mads-sprite', 'mads-tiles', 'mads-depth', 'mads-font', 'mads-dsr'):
        if adapter == 'mads-sprite': items, details = decode_sprites(data)
        elif adapter in ('mads-tiles', 'mads-depth'): items, details = decode_tiles(data, depth=adapter == 'mads-depth')
        elif adapter == 'mads-font': items, details = decode_font(data)
        else: items, details = decode_dsr(data)
        selected = (1 if adapter == 'mads-font' else 0) if number is None else number
        if items:
            if adapter == 'mads-font':
                bounded_int(selected, 'glyph code', 1, 127); index = selected-1
            else:
                bounded_int(selected, 'item index', 0, len(items)-1); index = selected
            if adapter == 'mads-dsr': sample = items[index]
            else: image = items[index]
            details['selected_index'] = selected
        else:
            require(number is None, 'Empty tile set has no selectable tile')
    elif adapter in ('mads-background', 'mads-depth-map'):
        require(map_path is not None, 'An explicit companion map_path is required')
        map_data = _source(map_path, map_member, inputs, 'map')
        image, details = decode_background(data, map_data, depth=adapter == 'mads-depth-map')
    elif adapter == 'mads-mask':
        image, details = decode_mask(data, width=width, height=height)
    else:
        details = decode_animation(data)
        payloads['timeline-json'] = (json.dumps(details, sort_keys=True, ensure_ascii=True, allow_nan=False)+'\n').encode()
    if image is not None:
        payloads['indices'] = image.pixels
        if image.palette is not None:
            payloads['palette-rgb'] = bytes(v for rgb in image.palette for v in rgb)
            if image.pixels: payloads['preview-png'] = image.png()
    if sample is not None:
        payloads['pcm-u8'] = sample.pcm
        payloads['audio-wav'] = sample.wav()
    require(sum(map(len, payloads.values())) <= 128*1024*1024, 'Prepared output budget exceeded')
    report = dict(format='fdisbull-media-members-1', adapter=adapter, adapter_version=1,
                  inputs=inputs, members=[dict(name=name, input_role='archive' if adapter == 'mads-hag' else 'container', offset=offsets.get(name),
                    input_roles=[item['role'] for item in inputs],
                    derived=name not in offsets, **identity(payload)) for name,payload in payloads.items()],
                  details=details, input_executed=False, qualification='decoded-media-not-runtime-equivalence',
                  specification='docs/MADS_MEDIA_RUNTIME.md',
                  unknowns=['No original-engine equivalence, live palette allocation, animation scheduling or native callbacks.'])
    return report, payloads


def main(argv=None):
    import argparse
    from .media import inspect_media, extract_media
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('catalog', 'inspect', 'extract'))
    parser.add_argument('path', nargs='?')
    parser.add_argument('--adapter', choices=NAMES)
    parser.add_argument('--number', type=int)
    source_choice = parser.add_mutually_exclusive_group()
    source_choice.add_argument('--source-member')
    source_choice.add_argument('--source-index', type=int)
    parser.add_argument('--map-path')
    map_choice = parser.add_mutually_exclusive_group()
    map_choice.add_argument('--map-member')
    map_choice.add_argument('--map-index', type=int)
    parser.add_argument('--expected-size', type=int)
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--output')
    parser.add_argument('--member')
    parser.add_argument('--max-output-bytes', type=int, default=64*1024*1024)
    args = parser.parse_args(argv)
    if args.source_index is not None:
        args.source_member = args.source_index
    if args.map_index is not None:
        args.map_member = args.map_index
    try:
        if args.operation == 'catalog': result = catalog()
        else:
            require(args.path is not None and args.adapter is not None, 'path and adapter are required')
            options = {key: value for key, value in vars(args).items() if key in
                       ('adapter','number','source_member','map_path','map_member','expected_size','width','height')
                       and value is not None}
            if args.operation == 'inspect': result = inspect_media(args.path, **options)
            else:
                require(args.output is not None and args.member is not None, 'output and member are required')
                result = extract_media(args.path, args.output, member=args.member,
                                       max_output_bytes=args.max_output_bytes, **options)
        print(json.dumps(dict(ok=True, result=result), ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, OSError) as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
