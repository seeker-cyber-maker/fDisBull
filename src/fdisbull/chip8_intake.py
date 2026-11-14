"""Pinned, byte-exact CHIP-8 conversion intake; no semantics are inferred."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from .chip8 import PROFILE, MEMORY_SIZE, ROM_BASE, MAX_ROM_SIZE
from .loader import load_image, MAX_IMAGE_SIZE
from .project import Project

FORMAT = 'fdisbull-chip8-conversion-intake-1'
_MAX_MANIFEST = 1024 * 1024
_HEX40 = re.compile(r'[0-9a-f]{40}\Z')
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_MEMBER = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
_ROOT = {'source_repo','source_commit','source_metadata_blob_sha','source_license','programs'}
_PROGRAM = {'key','title','author','platform','git_blob_sha','size','sha256'}


def _sha(data):return hashlib.sha256(data).hexdigest()
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _text(value,label,maximum=512):
    if (not isinstance(value,str) or not value.strip() or len(value)>maximum or
            any(ord(c)<32 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in value)):
        raise ValueError('Invalid CHIP-8 manifest '+label)
    return value


def _hex(value,pattern,label):
    if not isinstance(value,str) or not pattern.fullmatch(value):raise ValueError('Invalid CHIP-8 '+label)
    return value


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate CHIP-8 manifest key')
        result[key]=value
    return result


def _constant(value):raise ValueError('Nonfinite CHIP-8 manifest number')


def _manifest(data,pin):
    _hex(pin,_HEX64,'manifest SHA-256')
    if not isinstance(data,bytes) or not 0<len(data)<=_MAX_MANIFEST or _sha(data)!=pin:
        raise ValueError('CHIP-8 manifest size or SHA-256 differs')
    try:
        text=data.decode('utf-8',errors='strict')
        doc=json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error:
        raise ValueError('Invalid CHIP-8 manifest JSON') from error
    if not isinstance(doc,dict) or set(doc)!=_ROOT:raise ValueError('Invalid CHIP-8 manifest fields')
    repo=_text(doc['source_repo'],'repository',2048)
    try:url=urlsplit(repo);port=url.port
    except ValueError:raise ValueError('Invalid CHIP-8 manifest repository') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None or
            url.query or url.fragment or not url.path or any(c.isspace() for c in repo) or port is not None and not 1<=port<=65535):
        raise ValueError('CHIP-8 manifest repository must be a credential-free HTTPS URL')
    _hex(doc['source_commit'],_HEX40,'source commit')
    _hex(doc['source_metadata_blob_sha'],_HEX40,'source metadata blob')
    _text(doc['source_license'],'source license',1024)
    programs=doc['programs']
    if not isinstance(programs,list) or not 1<=len(programs)<=4096:raise ValueError('Invalid CHIP-8 manifest programs')
    seen=set()
    for item in programs:
        if not isinstance(item,dict) or not _PROGRAM<=item.keys() or set(item)-(_PROGRAM|{'edition'}):
            raise ValueError('Invalid CHIP-8 manifest program fields')
        key=item['key']
        if not isinstance(key,str) or not _MEMBER.fullmatch(key) or key in seen:raise ValueError('Invalid or duplicate CHIP-8 manifest member')
        seen.add(key)
        for name in ('title','author','platform'):_text(item[name],name)
        if 'edition' in item:_text(item['edition'],'edition')
        _hex(item['git_blob_sha'],_HEX40,'Git blob SHA-1');_hex(item['sha256'],_HEX64,'ROM SHA-256')
        if type(item['size']) is not int or not 1<=item['size']<=MAX_IMAGE_SIZE:
            raise ValueError('Invalid CHIP-8 manifest program size')
    return text,doc


def _manifest_file(path):
    if not hasattr(os,'O_NOFOLLOW') or not hasattr(os,'O_NONBLOCK'):
        raise ValueError('Safe regular CHIP-8 manifest admission is unavailable')
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
    try:
        fd=os.open(os.fspath(path),flags)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('CHIP-8 manifest must be a regular file')
            return stream.read(_MAX_MANIFEST+1)
    except OSError as error:raise ValueError('Cannot read a regular nonsymlink CHIP-8 manifest') from error


def _identity(doc,member,source,profile,manifest_sha256):
    if profile!=PROFILE:raise ValueError('Unsupported CHIP-8 conversion profile')
    if not isinstance(member,str) or not _MEMBER.fullmatch(member):raise ValueError('Invalid CHIP-8 corpus member')
    rows=[item for item in doc['programs'] if item['key']==member]
    if len(rows)!=1:raise ValueError('CHIP-8 corpus member not listed')
    item=rows[0]
    if item['platform']!='chip8':raise ValueError('CHIP-8 corpus member has incompatible declared platform')
    if not isinstance(source,bytes) or not 2<=len(source)<=MAX_ROM_SIZE:
        raise ValueError('Invalid CHIP-8 source bytes')
    blob=hashlib.sha1(b'blob '+str(len(source)).encode('ascii')+b'\0'+source).hexdigest()
    if len(source)!=item['size'] or _sha(source)!=item['sha256'] or blob!=item['git_blob_sha']:
        raise ValueError('CHIP-8 member size, SHA-256 or Git blob differs')
    return dict(format=FORMAT,gate='G0',status='exact-identity-verified',manifest_sha256=manifest_sha256,
        source=dict(sha256=item['sha256'],size=item['size'],git_blob_sha=blob,member=member,member_path='roms/'+member+'.ch8'),
        provenance=dict(source_repo=doc['source_repo'],source_commit=doc['source_commit'],
            source_metadata_blob_sha=doc['source_metadata_blob_sha'],source_license=doc['source_license'],
            title=item['title'],author=item['author'],platform=item['platform'],edition=item.get('edition')),
        profile=dict(id=PROFILE,architecture='chip8',bits=16,format='raw',rom_base=ROM_BASE,entry=ROM_BASE,
                     memory_size=MEMORY_SIZE,instruction_endian='big'),
        claims=dict(source='exact byte identity only',provenance='manifest-attributed; publisher authenticity and rights not independently verified',
                    semantics='not established',g1_g8='not run',
                    storage='required private content-addressed source object; no secondary working ROM copy'))


def create_intake(project,path,*,manifest_path,manifest_sha256,member,profile=PROFILE):
    """Verify both pinned inputs before creating a project or writing its objects."""
    raw=_manifest_file(manifest_path);text,doc=_manifest(raw,manifest_sha256)
    if profile!=PROFILE:raise ValueError('Unsupported CHIP-8 conversion profile')
    image=load_image(path,arch='chip8',profile=PROFILE)
    receipt=_identity(doc,member,image.source_bytes,profile,manifest_sha256)
    image.metadata['chip8_conversion_intake']=dict(manifest_text=text,manifest_sha256=manifest_sha256,member=member,
        receipt=receipt,intake_sha256=_sha(_canonical(receipt)))
    return Project._create_image(project,Path(path).name,image,loader_options={'arch':'chip8','profile':PROFILE})


def inspect_project(project,version=None,expected_manifest_sha256=None,expected_intake_sha256=None):
    """Revalidate stored source, mapping and pinned manifest without writing."""
    if project.db.in_transaction:raise ValueError('CHIP-8 intake inspection requires no caller transaction')
    selected=project.version(version)
    if selected['id']!=1 or selected.get('parent') is not None:raise ValueError('CHIP-8 conversion intake requires the original version')
    meta=project.meta
    for key in ('arch','bits','format','entry','source_sha256','loader_metadata','project_id'):
        row=project.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
        try:current=json.loads(row['value']) if row is not None else None
        except (ValueError,TypeError):raise ValueError('Invalid CHIP-8 project metadata') from None
        if current!=meta.get(key):raise ValueError('CHIP-8 cached project metadata differs from stored metadata')
    loader=meta.get('loader_metadata')
    if (meta.get('arch')!='chip8' or meta.get('bits')!=16 or meta.get('format')!='raw' or meta.get('entry')!=ROM_BASE or
            not isinstance(loader,dict) or loader.get('chip8_profile')!=PROFILE or loader.get('instruction_endian')!='big' or
            loader.get('mapping')!='flat' or loader.get('chip8')!=dict(profile=PROFILE,memory_size=MEMORY_SIZE,rom_base=ROM_BASE,instruction_bytes=2)):
        raise ValueError('CHIP-8 conversion project profile or mapping differs')
    stored=loader.get('chip8_conversion_intake')
    if not isinstance(stored,dict) or set(stored)!={'manifest_text','manifest_sha256','member','receipt','intake_sha256'}:
        raise ValueError('Missing CHIP-8 conversion intake evidence')
    if not isinstance(stored['manifest_text'],str):raise ValueError('Invalid CHIP-8 stored manifest')
    raw=stored['manifest_text'].encode('utf-8');_,doc=_manifest(raw,stored['manifest_sha256'])
    if expected_manifest_sha256 is not None and _hex(expected_manifest_sha256,_HEX64,'expected manifest SHA-256')!=stored['manifest_sha256']:
        raise ValueError('CHIP-8 expected manifest SHA-256 differs')
    source_info=project.source_info(selected['id'])
    if source_info.get('verified') is not True:raise ValueError('CHIP-8 original source is unavailable or unverified')
    if (source_info.get('arch')!='chip8' or source_info.get('bits')!=16 or source_info.get('format')!='raw' or
            source_info.get('loader_options')!={'arch':'chip8','profile':PROFILE}):
        raise ValueError('CHIP-8 original source loader identity differs')
    source=project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(selected['id'],)).fetchone()
    if source is None or source['source_bytes'] is None:raise ValueError('CHIP-8 original source bytes are unavailable')
    source=bytes(source['source_bytes']);receipt=_identity(doc,stored['member'],source,PROFILE,stored['manifest_sha256'])
    digest=_sha(_canonical(receipt))
    if receipt!=stored['receipt'] or digest!=stored['intake_sha256']:
        raise ValueError('CHIP-8 stored intake receipt or digest differs')
    if expected_intake_sha256 is not None and _hex(expected_intake_sha256,_HEX64,'expected intake SHA-256')!=digest:
        raise ValueError('CHIP-8 expected intake SHA-256 differs')
    if (source_info.get('identity')!=dict(size=len(source),sha256=_sha(source)) or meta.get('source_sha256')!=_sha(source) or
            loader.get('source_sha256')!=_sha(source) or loader.get('file_mappings')!=[dict(virtual_address=ROM_BASE,file_offset=0,file_size=len(source))]):
        raise ValueError('CHIP-8 original source identity or file mapping differs')
    regions=project.regions(selected['id'])
    if (len(regions)!=1 or regions[0].name!='chip8-rom' or regions[0].start!=ROM_BASE or regions[0].data!=source or
            not regions[0].executable or not regions[0].writable or project.digest(regions)!=selected['sha256']):
        raise ValueError('CHIP-8 mapped version differs from original source')
    return {**receipt,'intake_sha256':digest,'project':dict(id=meta['project_id'],version=selected['id'],mapped_sha256=selected['sha256'])}
