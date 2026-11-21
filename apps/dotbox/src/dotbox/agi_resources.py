# Extracted from first-party fDisBull v0.34.1; no license reassignment.
# Source commit: 011f1b8cb281edda208026aee9cdb238b800b2d7
# Original path: src/fdisbull/agi_resources.py
# Original SHA-256: a2d0cfa228279d4234211487eec81f9daccfe8c9e455ec4be9f5b886a833ea11
# https://github.com/seeker-cyber-maker/fDisBull/blob/011f1b8cb281edda208026aee9cdb238b800b2d7/src/fdisbull/agi_resources.py

"""Cached, bounded readers for the uncompressed DOS AGI version-2 format.

These readers recover source structure, not execution or publisher identity.
No engine/edition is inferred from a filename. The caller must qualify the
profile separately. Compressed AGI3, GAL/booters and SCI use other formats.

Format references (independently implemented here):
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/loader_v2.cpp
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/logic.cpp
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/words.cpp
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/objects.cpp
https://peterkelly.github.io/agi-re/spec/logic_bytecode.html
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path


_DIRECTORIES = {'logic': 'LOGDIR', 'picture': 'PICDIR',
                'view': 'VIEWDIR', 'sound': 'SNDDIR'}
_MAX_VOLUME = 2 * 1024 * 1024
_MESSAGE_KEY = b'Avis Durgan'
DEFAULT_MAX_MESSAGE_BYTES = 262144
MAX_MESSAGE_BYTES = 4194304


class TextBudgetExceeded(ValueError):
    """Literal expansion or unique text work exceeds the shared byte budget."""

    def __init__(self):
        super().__init__('Global expanded-text byte budget exhausted')
        self.partial = []
        self.total = None


class TextBudget:
    """Charge before text allocation; reuse shared source spans without rehashing.

    Literal occurrences count decoded single-byte characters, including aliases.
    Metadata-only LOGIC messages charge unique decrypted/hash work. JSON escape
    expansion has its own report-byte limit. Auxiliary words and OBJECT names
    share this budget with LOGIC messages.
    """

    def __init__(self, limit=DEFAULT_MAX_MESSAGE_BYTES):
        if type(limit) is not int or not 1 <= limit <= MAX_MESSAGE_BYTES:
            raise ValueError('max_message_bytes must be an integer in 1..4194304')
        self.limit = limit
        self.used = self.unique_bytes = self.cache_hits = 0
        self.spans = {}
        self.decoded = {}

    def reserve(self, size, *, constructed=0):
        if size > self.limit - self.used:
            raise TextBudgetExceeded()
        self.used += size
        self.unique_bytes += constructed

    def text(self, payload, start, end, origin, key, *, include_text, hash_text=True):
        cached = self.decoded.get(key)
        length = end - start
        if include_text or cached is None:
            self.reserve(length)
        if cached is None:
            # Admission precedes slicing, decryption, decoding and hashing.
            raw = bytes(payload[pos] ^ _MESSAGE_KEY[(pos - origin) % len(_MESSAGE_KEY)]
                        for pos in range(start, end))
            self.unique_bytes += length
            cached = {'raw': raw, 'length': length}
            if hash_text:
                cached['text_sha256'] = sha256(raw).hexdigest()
            self.decoded[key] = cached
        else:
            self.cache_hits += 1
        if include_text and 'text' not in cached:
            cached['text'] = cached['raw'].decode('cp437')
        return cached


def _encrypted_ends(payload, starts, limit, origin):
    """Locate terminators in one raw-byte pass, without expanding plaintext."""
    starts = sorted(set(starts))
    ends = {}
    next_start = 0
    if not starts:
        return ends
    for pos in range(starts[0], limit):
        if payload[pos] ^ _MESSAGE_KEY[(pos - origin) % len(_MESSAGE_KEY)]:
            continue
        while next_start < len(starts) and starts[next_start] <= pos:
            ends[starts[next_start]] = pos
            next_start += 1
        if next_start == len(starts):
            return ends
    raise ValueError('Text offset is not zero terminated')


class V2Resources:
    """Snapshot directory/volume bytes once and retain per-resource failures.

The four directories contain at most 256 entries each and select at most 16
volumes, each bounded to 2 MiB. Missing or malformed directories are explicit
in ``manifest()``. One broken resource does not discard other census entries.
Optional WORDS.TOK and encrypted DOS OBJECT files are each bounded to 65535
bytes; their failures remain separate from the four-directory resource census.
This is a snapshot of individual files, not an atomic filesystem transaction;
the manifest binds every successful read to the bytes actually used.
Returned payloads/messages are private game-derived material.
"""

    def __init__(self, root, *, text_budget=None, include_text=True):
        self._text_budget = text_budget if text_budget is not None else TextBudget()
        self._include_text = include_text
        root = Path(root)
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            raise ValueError('Cannot enumerate AGI resource directory') from exc
        self._names = {}
        for path in children:
            self._names.setdefault(path.name.upper(), []).append(path)
        self._read_counts = {}
        self._directories = []
        self._volumes = {}
        self._entries = {}
        self._resource_cache = {}
        for kind, filename in _DIRECTORIES.items():
            source = self._read(filename, 768)
            data = source.pop('data', None)
            directory = {'kind': kind, **source}
            self._directories.append(directory)
            self._entries[kind] = []
            if data is None:
                continue
            if len(data) % 3:
                directory.update(status='error', error='Directory length is not a multiple of three')
                continue
            directory.update(entries=len(data) // 3, present=0)
            for number in range(len(data) // 3):
                entry = int.from_bytes(data[3 * number:3 * number + 3], 'big')
                volume, offset = entry >> 20, entry & 0xfffff
                if offset == 0xfffff:
                    continue
                directory['present'] += 1
                record = self._resource(volume, offset)
                self._entries[kind].append({'kind': kind, 'number': number, **record})
        self._vocabulary = self._optional('WORDS.TOK', _vocabulary,
                                          {'groups': [], 'entries': []})
        self._objects = self._optional('OBJECT', _objects, {'objects': []})

    def _read(self, filename, limit):
        result = {'filename': filename}
        matches = self._names.get(filename, [])
        if not matches:
            return {**result, 'status': 'absent'}
        if len(matches) != 1:
            return {**result, 'status': 'error', 'error': 'Ambiguous case-insensitive filename'}
        try:
            if not matches[0].is_file():
                return {**result, 'status': 'error', 'error': 'Expected a regular file'}
            self._read_counts[filename] = self._read_counts.get(filename, 0) + 1
            with matches[0].open('rb') as stream:
                data = stream.read(limit + 1)
        except OSError:
            return {**result, 'status': 'error', 'error': 'File read failed'}
        if len(data) > limit:
            return {**result, 'status': 'error', 'error': f'File exceeds {limit}-byte limit'}
        return {**result, 'status': 'ok', 'size': len(data),
                'sha256': sha256(data).hexdigest(), 'data': data}

    def _resource(self, volume, offset):
        key = (volume, offset)
        if key in self._resource_cache:
            return self._resource_cache[key]
        if volume not in self._volumes:
            self._volumes[volume] = {'number': volume,
                                     **self._read(f'VOL.{volume}', _MAX_VOLUME)}
        source = self._volumes[volume]
        result = {'volume': volume, 'offset': offset, 'status': 'error'}
        if source['status'] != 'ok':
            result['error'] = ('Missing volume' if source['status'] == 'absent'
                               else source['error'])
        else:
            data = source['data']
            if offset + 5 > len(data):
                result['error'] = 'Truncated v2 resource header'
            elif data[offset:offset + 2] != b'\x12\x34':
                result['error'] = 'Invalid v2 resource signature'
            elif data[offset + 2] != volume:
                result['error'] = 'Volume header number mismatch'
            else:
                length = int.from_bytes(data[offset + 3:offset + 5], 'little')
                result['length'] = length
                if offset + 5 + length > len(data):
                    result['error'] = 'Truncated resource payload'
                else:
                    payload = data[offset + 5:offset + 5 + length]
                    result.update(status='ok', payload=payload,
                                  sha256=sha256(payload).hexdigest())
        self._resource_cache[key] = result
        return result

    def resources(self, kind):
        """Return present entries in directory-number order, including errors."""
        if type(kind) is not str or kind not in _DIRECTORIES:
            raise ValueError('Resource kind must be logic, picture, view or sound')
        return deepcopy(self._entries[kind])

    def _optional(self, filename, decoder, empty):
        source = self._read(filename, 65535)
        data = source.pop('data', None)
        result = {'status': source['status'], **empty, 'source': source}
        if data is None:
            if 'error' in source:
                result['error'] = source['error']
            return result
        try:
            return {**result, **decoder(data, budget=self._text_budget,
                                       include_text=self._include_text,
                                       source_key=(filename, source['sha256'])), 'status': 'decoded'}
        except TextBudgetExceeded as exc:
            return {**result, 'status': 'budget', 'error': str(exc),
                    'budget_scope': 'expanded_text_bytes'}
        except ValueError as exc:
            return {**result, 'status': 'error', 'error': str(exc)}

    def vocabulary(self):
        """Return literal synonyms and typed word-group roles, not a grammar.

        ``lookup_indexed`` says that a source alphabet index reaches the word's
        prefix-compression chain. It does not assert native parser acceptance.
        Unindexed entries remain visible, including special wildcard labels.
        """
        return deepcopy(self._vocabulary)

    def objects(self):
        """Return literal inventory names and encoded initial locations.

        The explicit profile is Avis Durgan encryption with three-byte DOS
        records. No plaintext/Amiga/alternate-key heuristic is attempted.
        Inventory object IDs are separate from animated screen-object IDs.
        """
        return deepcopy(self._objects)

    def manifest(self):
        """Return immutable-source identities and coverage, without file paths."""
        return deepcopy({
            'format': 'fdisbull-agi-v2-resources-1',
            'directories': self._directories,
            'volumes': [{k: v for k, v in self._volumes[n].items() if k != 'data'}
                        for n in sorted(self._volumes)],
            'auxiliary': [{**item['source'], 'decode_status': item['status'],
                           **({'error': item['error']} if 'error' in item else {})}
                          for item in (self._vocabulary, self._objects)],
            'read_counts': dict(sorted(self._read_counts.items())),
        })


def _vocabulary(data, *, budget=None, include_text=True, source_key=None):
    budget = budget if budget is not None else TextBudget()
    copies = 2 if include_text else 1  # Group words and entry words are both emitted.
    if len(data) < 52:
        raise ValueError('Truncated WORDS.TOK alphabet header')
    indexes = [int.from_bytes(data[i:i + 2], 'big') for i in range(0, 52, 2)]
    entries = []
    starts = {}
    previous = ''
    cursor = 52
    while cursor < len(data):
        start = cursor
        prefix = data[cursor]
        cursor += 1
        if cursor == len(data) and prefix == 0:
            break
        if prefix > len(previous):
            raise ValueError('WORDS.TOK prefix exceeds previous word length')
        budget.reserve(copies * prefix, constructed=prefix)
        word = previous[:prefix]
        while True:
            if cursor >= len(data):
                raise ValueError('Truncated WORDS.TOK word')
            encoded = data[cursor]
            cursor += 1
            value = (encoded ^ 0x7f) & 0x7f
            if not 32 <= value <= 126 or len(word) >= 63:
                raise ValueError('Unsupported WORDS.TOK character or word length')
            budget.reserve(copies, constructed=1)
            word += chr(value)
            if encoded & 0x80:
                break
        if cursor + 2 > len(data):
            raise ValueError('Truncated WORDS.TOK word-group number')
        number = int.from_bytes(data[cursor:cursor + 2], 'big')
        cursor += 2
        starts[start] = len(entries)
        entries.append({'offset': start, 'number': number, 'word': word,
                        'lookup_indexed': False, '_prefix': prefix})
        previous = word
    for letter, offset in enumerate(indexes):
        if not offset:
            continue
        if offset not in starts:
            raise ValueError('WORDS.TOK alphabet index is not a word boundary')
        index = starts[offset]
        first = entries[index]
        if first['_prefix'] != 0 or first['word'][0] != chr(97 + letter):
            raise ValueError('WORDS.TOK alphabet index has an unsupported letter or prefix')
        while index < len(entries):
            item = entries[index]
            if index != starts[offset] and item['_prefix'] == 0:
                break
            item['lookup_indexed'] = True
            index += 1
    groups = {}
    roles = {0: 'ignored', 1: 'any_word', 9999: 'rest_of_input'}
    for item in entries:
        item.pop('_prefix')
        group = groups.setdefault(item['number'], {
            'number': item['number'], 'words': [],
            'role': roles.get(item['number'], 'word_group')})
        group['words'].append(item['word'])
    return {'groups': [groups[n] for n in sorted(groups)], 'entries': entries}


def _objects(data, *, budget=None, include_text=True, source_key=None):
    budget = budget if budget is not None else TextBudget()
    if len(data) < 3:
        raise ValueError('Invalid encrypted OBJECT length')
    def byte(pos):
        return data[pos] ^ _MESSAGE_KEY[pos % len(_MESSAGE_KEY)]
    def word(pos):
        return byte(pos) | byte(pos + 1) << 8
    table_size = word(0)
    if table_size % 3 or table_size > 256 * 3 or table_size + 3 > len(data):
        raise ValueError('Invalid DOS OBJECT record table')
    names_start = 3 + table_size
    records = []
    for number in range(table_size // 3):
        record = 3 + 3 * number
        start = 3 + word(record)
        if not names_start <= start < len(data):
            raise ValueError(f'OBJECT {number} name offset is outside the string area')
        records.append((number, start, byte(record + 2)))
    ends = _encrypted_ends(data, [row[1] for row in records], len(data), 0)
    result = []
    for number, start, initial_room in records:
        item = {'number': number, 'initial_room': initial_room}
        if include_text:
            decoded = budget.text(data, start, ends[start], 0,
                                  ('object', source_key, start, ends[start]),
                                  include_text=True, hash_text=False)
            item['name'] = decoded['text']
        result.append(item)
    return {'objects': result, 'max_animated_objects': byte(2)}


def _logic_messages_payload(payload, *, include_text=True, budget=None, source_key=None):
    """Decode literal message templates in an uncompressed v2 logic payload.

Offsets are relative to the payload, not a volume, native address or code PC.
Messages keep their original one-based numbers. Absent slots have ``None``
text/offset; identical or suffix-sharing pointers are allowed. Cipher state
starts at the shared string area and does not restart for each message.
CP437 rendering is lossless for bytes but does not expand engine substitutions
or certify the target's language/font. Unexpected framing is refused explicitly.
"""
    budget = budget if budget is not None else TextBudget()
    if not isinstance(payload, bytes) or not 2 <= len(payload) <= 65535:
        raise ValueError('Invalid AGI logic resource length')
    cache_key = ('logic', source_key)
    if source_key is not None and cache_key in budget.spans:
        strings_start, spans = budget.spans[cache_key]
        return _message_rows(payload, strings_start, spans, budget, cache_key, include_text)
    code_length = int.from_bytes(payload[:2], 'little')
    if not code_length:
        raise ValueError('Invalid AGI code length')
    message_start = 2 + code_length
    if message_start + 3 > len(payload):
        raise ValueError('Truncated message section')
    count = payload[message_start]
    table_base = message_start + 1
    strings_start = table_base + 2 + 2 * count
    if strings_start > len(payload):
        raise ValueError('Truncated message offset table')
    section_size = int.from_bytes(payload[table_base:table_base + 2], 'little')
    section_end = table_base + section_size
    if not strings_start <= section_end <= len(payload):
        raise ValueError('Invalid message section size')
    if section_end != len(payload):
        raise ValueError('Unsupported trailing bytes after message section')
    pointers = []
    for number in range(1, count + 1):
        pointer = table_base + 2 * number
        offset = int.from_bytes(payload[pointer:pointer + 2], 'little')
        if not offset:
            pointers.append((number, None))
            continue
        start = table_base + offset
        if not strings_start <= start < section_end:
            raise ValueError(f'Message {number} offset is outside the string area')
        pointers.append((number, start))
    ends = _encrypted_ends(payload, [start for _, start in pointers if start is not None],
                           section_end, strings_start)
    spans = [(number, start, ends.get(start)) for number, start in pointers]
    if source_key is not None:
        budget.spans[cache_key] = (strings_start, spans)
    return _message_rows(payload, strings_start, spans, budget, cache_key, include_text)


def _message_rows(payload, strings_start, spans, budget, cache_key, include_text):
    result = []
    try:
        for number, start, end in spans:
            if start is None:
                item = {'number': number, 'offset': None, 'length': None, 'text_sha256': None}
                if include_text:
                    item['text'] = None
            else:
                decoded = budget.text(payload, start, end, strings_start, (*cache_key, start, end),
                                      include_text=include_text)
                item = {'number': number, 'offset': start, 'length': decoded['length'],
                        'text_sha256': decoded['text_sha256']}
                if include_text:
                    item['text'] = decoded['text']
            result.append(item)
    except TextBudgetExceeded as error:
        error.partial = result
        error.total = len(spans)
        raise
    return result

def view_metadata(payload):
    if type(payload) is not bytes or not 5 <= len(payload) <= 65535:
        raise ValueError('invalid bounded v2 VIEW payload')
    def word(pos):
        if not 0 <= pos <= len(payload)-2:raise ValueError('truncated VIEW offset')
        return int.from_bytes(payload[pos:pos+2],'little')
    count=payload[2];description=word(3)
    if not count or 5+2*count>len(payload):raise ValueError('invalid VIEW loop directory')
    if description and (description>=len(payload) or b'\x00' not in payload[description:]):
        raise ValueError('invalid VIEW description')
    loops=[];total=0
    for index in range(count):
        start=word(5+index*2)
        if not 5+2*count <= start < len(payload):raise ValueError('invalid VIEW loop offset')
        cels=payload[start];total+=cels
        if not cels or total>1024 or start+1+2*cels>len(payload):
            raise ValueError('invalid VIEW cel directory or cel budget')
        result=[]
        for number in range(cels):
            cel=start+word(start+1+2*number)
            if cel<start+1+2*cels or cel+3>len(payload):raise ValueError('invalid VIEW cel offset')
            width,height=payload[cel:cel+2]
            if not 1<=width<=160 or not 1<=height<=168:raise ValueError('invalid VIEW dimensions')
            cursor=cel+3
            for _ in range(height):
                drawn=0
                while True:
                    if cursor>=len(payload):raise ValueError('truncated VIEW cel rows')
                    run=payload[cursor];cursor+=1
                    if run==0:break
                    length=run&15
                    if not length or drawn+length>width:raise ValueError('invalid VIEW run length')
                    drawn+=length
            result.append({'width':width,'height':height})
        loops.append(result)
    return {'sha256':sha256(payload).hexdigest(),'loops':loops}


def bind_native_view(source, runtime):
    """Bind unchanged bytes or a narrowly source-derived aliased mirror cache.

    AGI 2.917 mirrors some shared cels in place, changing their encoded rows
    and original-loop selector. Source bytes remain authoritative. This checks
    geometry and every effective loop/cel image, not the identity of a writer.
    All other bytes must match; this is not a general pixel-equivalence test.
    """
    view_metadata(source)
    if type(runtime) is not bytes or len(runtime)!=len(source):
        raise ValueError('native VIEW length differs')
    evidence={'source_sha256':sha256(source).hexdigest(),
              'runtime_sha256':sha256(runtime).hexdigest(),
              'byte_identical':source==runtime,'relation':'byte-identical','changed_cels':[]}
    if source==runtime:return evidence
    view_metadata(runtime)
    count=source[2];directory=5+2*count
    if source[:directory]!=runtime[:directory]:raise ValueError('native VIEW directory differs')
    word=lambda p:int.from_bytes(source[p:p+2],'little')
    aliases={};protected=[(0,directory)];boundaries={len(source)}
    description=word(3)
    if description:
        boundaries.add(description)
        protected.append((description,source.index(b'\0',description)+1))
    for loop in range(count):
        start=word(5+2*loop);end=start+1+2*source[start]
        if source[start:end]!=runtime[start:end]:raise ValueError('native VIEW cel directory differs')
        protected.append((start,end));boundaries.add(start)
        for cel in range(source[start]):
            address=start+word(start+1+2*cel)
            aliases.setdefault(address,set()).add(loop);boundaries.add(address)
    work=0
    allowed=bytearray(len(source))
    def decode(payload,start,limit):
        nonlocal work
        width,height,flags=payload[start:start+3];cursor=start+3;rows=[]
        work+=width*height
        if work>2*1024*1024:raise ValueError('native VIEW pixel budget exhausted')
        for _ in range(height):
            row=[]
            while True:
                if cursor>=limit:raise ValueError('native VIEW cel overlaps another structure')
                run=payload[cursor];cursor+=1
                if not run:break
                length=run&15
                if not length or len(row)+length>width:raise ValueError('invalid native VIEW run')
                row.extend([run>>4]*length)
            row.extend([flags&15]*(width-len(row)));rows.append(tuple(row))
        return tuple(rows),cursor
    ordered=sorted(boundaries)
    for start,loops in sorted(aliases.items()):
        limit=next(p for p in ordered if p>start)
        if start+3>limit:raise ValueError('native VIEW header overlaps another structure')
        if source[start:start+2]!=runtime[start:start+2]:raise ValueError('native VIEW dimensions differ')
        a,b=source[start+2],runtime[start+2]
        old,_=decode(source,start,limit);new,_=decode(runtime,start,limit)
        if source[start:limit]==runtime[start:limit]:continue
        old_loop,new_loop=(a>>4)&7,(b>>4)&7
        if not a&0x80 or a&0x8f!=b&0x8f or len(loops)<2 or old_loop not in loops or new_loop not in loops:
            raise ValueError('native VIEW is not an aliased mirror cache')
        expected=old if old_loop==new_loop else tuple(row[::-1] for row in old)
        if new!=expected:raise ValueError('native VIEW pixels differ')
        for loop in loops:
            work+=len(old)*len(old[0])
            if work>2*1024*1024:raise ValueError('native VIEW pixel budget exhausted')
            left=tuple(row[::-1] for row in old) if old_loop!=loop else old
            right=tuple(row[::-1] for row in new) if new_loop!=loop else new
            if left!=right:raise ValueError('native VIEW effective image differs')
        for p,q in protected:
            if start<q and p<limit:raise ValueError('native VIEW overlaps protected structure')
        # Re-encoding can grow into reserved cel space or leave unused tails.
        # These bytes are retained as a distinct runtime version, never called
        # identical to source. The next structural pointer bounds the allowance.
        allowed[start+2:limit]=b'\x01'*(limit-start-2)
        evidence['changed_cels'].append({'offset':start,'from_loop':old_loop,'to_loop':new_loop,'aliases':sorted(loops)})
    if not evidence['changed_cels'] or any(a!=b and not allowed[i] for i,(a,b) in enumerate(zip(source,runtime))):
        raise ValueError('native VIEW has changes outside mirrored cels')
    evidence['relation']='aliased-mirror-cache'
    return evidence


def capture_view(viewdir, volume_dir, view, *, profile):
    if profile!='2.917' or type(view) is not int or not 0<=view<=255:
        raise ValueError('explicit v2.917 profile and byte view ID required')
    with Path(viewdir).open('rb') as stream:directory=stream.read(769)
    if len(directory)>768 or len(directory)%3 or view*3+3>len(directory):
        raise ValueError('invalid VIEWDIR or absent entry')
    entry=int.from_bytes(directory[view*3:view*3+3],'big');volume=entry>>20;offset=entry&0xfffff
    if offset==0xfffff:raise ValueError('view resource absent')
    matches=[p for p in Path(volume_dir).iterdir() if p.is_file() and p.name.lower()==f'vol.{volume}']
    if len(matches)!=1:raise ValueError('expected exactly one VIEW volume')
    with matches[0].open('rb') as stream:data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or offset+5>len(data) or data[offset:offset+3]!=b'\x12\x34'+bytes([volume]):
        raise ValueError('invalid or oversized VIEW volume')
    size=int.from_bytes(data[offset+3:offset+5],'little');end=offset+5+size
    if end>len(data):raise ValueError('truncated VIEW resource')
    metadata=view_metadata(data[offset+5:end])
    return {'view':view,'profile':profile,'metadata':metadata,
            'directory_sha256':sha256(directory).hexdigest(),
            'volume_sha256':sha256(data).hexdigest(),'resource_offset':offset,'resource_length':size}


def logic_messages(payload, *, include_text=True, max_message_bytes=DEFAULT_MAX_MESSAGE_BYTES,
                   _budget=None, _source_key=None):
    """Decode messages from raw bytes or a bound resource object."""
    budget = _budget if _budget is not None else TextBudget(max_message_bytes)
    if hasattr(payload, 'payload') and hasattr(payload, 'resource_sha256'):
        rows = _logic_messages_payload(payload.payload, include_text=include_text,
                                       budget=budget, source_key=payload.resource_sha256)
        return {payload.resource_sha256: {
            str(row['number']): row['text'] for row in rows if row.get('text') is not None
        }}
    return _logic_messages_payload(payload, include_text=include_text,
                                   budget=budget, source_key=_source_key)
