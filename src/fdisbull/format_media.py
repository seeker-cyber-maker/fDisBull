"""Bounded headers for resource formats observed during private game intake.

These authored probes identify structure, not payload semantics or safe editing.
Headerless families are separate context candidates in the format catalog.
"""
from __future__ import annotations
import struct


def definitions(make, field, magic):
    rows = [
        ('iff', 'IFF FORM / LIST / CAT', 'container', [magic(0,b'FORM'),magic(0,b'LIST'),magic(0,b'CAT ')],
         [field('chunk_bytes',4,'u32be','First top-level chunk payload'),field('form_type',8,'fourcc','ILBM/PBM image, XDIR/XMID music, 8SVX audio, or other subtype')], 'big',
         'Top-level chunk extent/subtype only; nested chunks, image/audio/music payloads and subsequent top-level chunks need separate readers.', 'https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/iff.c'),
        ('midi','Standard MIDI file','music',[magic(0,b'MThd')],
         [field('header_bytes',4,'u32be','At least six'),field('format',8,'u16be','0, 1 or 2'),field('tracks',10,'u16be','Declared track count'),field('division',12,'u16be','Ticks or SMPTE encoding')], 'big',
         'Header only; no event stream, instrument bank, synth or timing qualification.', 'https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/smfdec.c'),
        ('voc','Creative Voice File','audio',[magic(0,b'Creative Voice File\x1a')],
         [field('data_offset',20,'u16le','First block'),field('version',22,'u16le','Version word'),field('version_check',24,'u16le','Complement version plus 0x1234')], 'little',
         'Header/checksum only; block codecs and complete audio decode are unsupported here.', 'https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/vocdec.c'),
        ('pcx','PC Paintbrush PCX','image',[magic(0,b'\x0a')],
         [field('version',1,'u8','Version 0..5'),field('encoding',2,'u8','Raw or RLE'),field('bits_per_plane',3,'u8','1,2,4,8'),field('bounds',4,'4*u16le','Inclusive xmin/ymin/xmax/ymax'),field('planes',65,'u8','Planes'),field('bytes_per_line',66,'u16le','Padded scanline per plane')], 'little',
         'Compound 128-byte header probe only; palette/RLE/pixels require a separate reader.', 'https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/pcx.c'),
        ('dinopark-picture','DinoPark UNCP picture container','image-container',[magic(0,b'UNCP')],
         [field('first_frame',4,'u32le','First offset implies (first-4)/4 directory entries'),field('frame_offsets',4,'u32le[]','Absolute frame offsets')], 'little',
         'Directory/first-frame geometry only; full row decoding, palette/rendering and rewriting are separate. This is not Civilization PIC or FLI.', 'docs/TARGET_COLLECTION_INTAKE.md'),
        ('dinopark-actor','DinoPark UNC2 / UNCS actor container','animation-container',[magic(0,b'UNC2'),magic(0,b'UNCS')],
         [field('sprites',4,'u16le','Sprite count'),field('directory',6,'u32le/UNC2','Absolute trailing directory; UNCS has no directory'),field('sequences','10/UNC2 or6/UNCS','u16le','Sequence count')], 'little',
         'Header/directory envelope only; sprite opacity/command streams and sequence control flow need separate qualification; never frame as FLI.', 'docs/TARGET_COLLECTION_INTAKE.md'),
    ]
    return [make(i,n,c,s,f,endian=e,limitations=[l],provenance=[p]) for i,n,c,s,f,e,l,p in rows]


def probe(prefix, reader):
    from .format_registry import _result, MAX_TABLE_BYTES
    if prefix[:4] in (b'FORM',b'LIST',b'CAT '):
        valid=len(prefix)>=12
        meta={}
        if valid:
            amount=int.from_bytes(prefix[4:8],'big'); subtype=prefix[8:12].decode('ascii','replace')
            valid=amount>=4 and 8+amount<=reader.size
            meta=dict(container=prefix[:4].decode(),subtype=subtype,first_chunk_bytes=amount,
                first_chunk_end=8+amount,trailing_bytes=max(0,reader.size-(8+amount)),nested_chunks_decoded=False)
        return _result('iff','IFF container','container',valid=valid,metadata=meta,
            warnings=['Nested chunks and format-specific image/music/audio payloads are unqualified'])
    if prefix[:4]==b'MThd':
        valid=len(prefix)>=14;meta={}
        if valid:
            length=int.from_bytes(prefix[4:8],'big');kind,tracks,division=struct.unpack_from('>3H',prefix,8)
            valid=6<=length<=reader.size-8 and kind<=2 and tracks>0 and division!=0 and (kind!=0 or tracks==1)
            meta=dict(header_bytes=length,midi_format=kind,tracks=tracks,division=division)
        return _result('midi','Standard MIDI','music',valid=valid,metadata=meta)
    if prefix.startswith(b'Creative Voice File\x1a'):
        valid=len(prefix)>=26;meta={}
        if valid:
            offset,version,check=struct.unpack_from('<3H',prefix,20)
            valid=26<=offset<=reader.size and check==((~version+0x1234)&65535)
            meta=dict(data_offset=offset,version=version,version_check=check)
        return _result('voc','Creative Voice File','audio',valid=valid,metadata=meta)
    # A single 0x0a is too weak: require the compound PCX fields before claiming it.
    if len(prefix)>=128 and prefix[0]==10 and prefix[1]<=5 and prefix[2] in (0,1) and prefix[3] in (1,2,4,8):
        xmin,ymin,xmax,ymax=struct.unpack_from('<4H',prefix,4)
        planes=prefix[65];stride=int.from_bytes(prefix[66:68],'little')
        if xmax>=xmin and ymax>=ymin and 1<=planes<=4 and stride>0 and stride*8>=(xmax-xmin+1)*prefix[3]:
            return _result('pcx','PC Paintbrush PCX','image',metadata=dict(width=xmax-xmin+1,height=ymax-ymin+1,
                bits_per_plane=prefix[3],planes=planes,bytes_per_line=stride,encoding=prefix[2]))
    if prefix[:4]==b'UNCP':
        valid=len(prefix)>=8;meta={}
        if valid:
            first=int.from_bytes(prefix[4:8],'little');count=(first-4)//4
            valid=first>=8 and first%4==0 and first<=reader.size and 1<=count<=MAX_TABLE_BYTES//4
            meta=dict(first_frame_offset=first,directory_entries=count)
            if valid:
                raw=reader.read(4,4*count);offsets=[v[0] for v in struct.iter_unpack('<I',raw)]
                valid=len(raw)==4*count and all(a<b for a,b in zip(offsets,offsets[1:])) and all(first<=v<reader.size for v in offsets)
                meta['directory_extents_checked']=valid
                if valid:
                    frame=reader.read(first,8)
                    if len(frame)==8:
                        size,width,height=struct.unpack('<I2H',frame)
                        frame_end=offsets[1] if count>1 else reader.size
                        valid=width>0 and height>0 and size>=774 and first+4+size==frame_end
                        meta.update(first_frame_bytes_excluding_length=size,width=width,height=height,
                            first_frame_extent_checked=valid)
                    else:valid=False
        return _result('dinopark-picture','DinoPark UNCP picture','image-container',valid=valid,metadata=meta,
            warnings=['Directory/first-frame fields only; pixel decoding and safe editing unqualified'])
    if prefix[:4] in (b'UNC2',b'UNCS'):
        header=14 if prefix[:4]==b'UNC2' else 10
        valid=len(prefix)>=header;meta={}
        if valid:
            count=int.from_bytes(prefix[4:6],'little');seq,seq_bytes=struct.unpack_from('<2H',prefix,header-4)
            valid=1<=count<=8192
            meta=dict(variant=prefix[:4].decode(),header_bytes=header,sprites=count,sequences=seq,sequence_bytes=seq_bytes)
            if header==14:
                directory=int.from_bytes(prefix[6:10],'little');meta['directory_offset']=directory
                valid=valid and directory>=header and directory+4*count==reader.size
            else:valid=valid and header+16*count+seq_bytes<=reader.size
        return _result('dinopark-actor','DinoPark actor container','animation-container',valid=valid,metadata=meta,
            warnings=['Sprite command, opacity and sequence interpretation require a separate decoder'])
    return None
