"""Identify independently selectable DOS and PE views of retained file bytes.

A secondary header does not replace the preceding DOS image. View discovery is
read-only and never executes or extracts a guessed stub. A DOS view is loadable
only if the ordinary MZ validation succeeds; a PE view's structural validation
is a bounded header/table check, with mapping/entry validation left to import.
"""
from __future__ import annotations

import struct

_MAX_SOURCE=64*1024*1024


def _source(data):
    if not isinstance(data,bytes):raise ValueError('image-view discovery requires immutable bytes')
    if len(data)>_MAX_SOURCE:raise ValueError('image-view source exceeds the 64 MiB limit')
    return data


def secondary_header(data:bytes)->dict|None:
    """Recognize an actual independent e_lfanew secondary-header signature.

    Old DOS relocation records may occupy bytes 0x3c..0x3f. In that case the
    bytes are not an independent e_lfanew field and do not select another image.
    Header validation of the secondary format is separate from recognition.
    """
    data=_source(data)
    if not data.startswith(b'MZ') or len(data)<64:return None
    count=struct.unpack_from('<H',data,6)[0]
    relocation_offset=struct.unpack_from('<H',data,24)[0]
    if count and relocation_offset<64 and relocation_offset+count*4>60:return None
    offset=struct.unpack_from('<I',data,60)[0]
    if offset<64 or offset+2>len(data):return None
    signature=data[offset:offset+4]
    for marker,kind in ((b'PE\0\0','PE'),(b'NE','NE'),(b'LE','LE'),(b'LX','LX')):
        if signature.startswith(marker):return dict(format=kind,header_offset=offset)
    return None


def _pe_view(data,offset):
    view=dict(image='pe',format='PE',header_offset=offset,arch=None,bits=None,
              endian='little',available=False,valid=False,error=None,
              validation_scope='PE structural header/table extents; import validates native mappings and entry')
    def need(end,label):
        if end>len(data):raise ValueError('truncated PE '+label)
    try:
        need(offset+24,'COFF header')
        machine,count=struct.unpack_from('<HH',data,offset+4)
        optional_size=struct.unpack_from('<H',data,offset+20)[0]
        optional=offset+24
        view.update(machine=machine,section_count=count,optional_header_size=optional_size)
        if optional_size<2:raise ValueError('PE optional header has no complete magic')
        need(optional+optional_size,'optional header')
        magic=struct.unpack_from('<H',data,optional)[0]
        if magic not in (0x10b,0x20b):raise ValueError('unsupported PE optional-header magic')
        bits=64 if magic==0x20b else 32
        view.update(bits=bits,arch={0x14c:'x86',0x8664:'x86',0xaa64:'arm64'}.get(machine,f'machine:{machine:#x}'))
        minimum=112 if bits==64 else 96
        if optional_size<minimum:raise ValueError('PE optional header is smaller than its format minimum')
        if count>4096:raise ValueError('PE section count exceeds 4096')
        header_end=optional+optional_size+count*40
        need(header_end,'section table')
        imagebase=struct.unpack_from('<Q' if bits==64 else '<I',data,optional+(24 if bits==64 else 28))[0]
        entry_rva=struct.unpack_from('<I',data,optional+16)[0]
        if imagebase+entry_rva>=1<<64:raise ValueError('PE entry address exceeds the 64-bit address space')
        extent=header_end
        for index in range(count):
            section=optional+optional_size+index*40
            raw_size,raw_offset=struct.unpack_from('<II',data,section+16)
            if raw_size:
                need(raw_offset+raw_size,'section data')
                extent=max(extent,raw_offset+raw_size)
        view.update(imagebase=imagebase,entry_rva=entry_rva,entrypoint=imagebase+entry_rva,
                    header_end=header_end,file_extent_start=offset,file_extent_end=extent,
                    valid=True)
        if machine not in (0x14c,0x8664,0xaa64):
            raise ValueError('unsupported PE architecture for native analysis')
        if (machine==0x14c and bits!=32) or (machine in (0x8664,0xaa64) and bits!=64):
            raise ValueError('PE machine and optional-header bitness disagree')
        view['available']=True
    except ValueError as error:
        view['error']=str(error)
    return view


def image_views(data:bytes)->list[dict]:
    """Return recognized DOS/PE selectors without replacing or executing bytes.

    MZ loadability is checked at the ordinary default load segment 0x1000. An
    invalid classic stub is retained as an unavailable DOS view alongside a
    structurally valid PE view. NE/LE/LX remain recognized secondary metadata,
    not supported native image selectors. Other container inventories belong
    to their own format adapters.
    """
    data=_source(data)
    if not data.startswith(b'MZ'):return []
    secondary=secondary_header(data)
    mz=dict(image='mz',format='MZ',header_offset=0,arch='x86',bits=16,endian='little',
            available=False,loadable=False,valid=False,error=None,load_segment=0x1000,
            secondary_format=secondary['format'] if secondary else None,
            secondary_header_offset=secondary['header_offset'] if secondary else None,
            validation_scope='classic DOS load validation at load segment 0x1000')
    from .dos import load_mz
    try:
        loaded=load_mz(data,allow_secondary=True)
        dos=loaded.metadata['dos']
        mz.update(available=True,loadable=True,valid=True,entrypoint=loaded.entry,
                  entry_cs=dos['selected_entry_cs'],entry_ip=dos['selected_entry_ip'],
                  header_size=dos['header_size'],module_file_offset=dos['header_size'],
                  module_file_size=dos['module_size'],declared_file_size=dos['declared_file_size'],
                  allocation_size=dos['allocation_size'],overlay_size=dos['overlay_size'])
    except ValueError as error:
        mz['error']=str(error)
    views=[mz]
    if secondary and secondary['format']=='PE':views.append(_pe_view(data,secondary['header_offset']))
    return views
