"""Recover shipped Miniplanets Sona streams and arrange their events for NES APU.

Audio events and logical stream completion are preserved separately from the
five-channel hardware arrangement. FM/PSG timbre and polyphony are adaptations.
Original byte ranges are identified by hashes; no game audio is bundled here.
"""
from __future__ import annotations

import hashlib
import math


ROM_SHA256 = 'e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7'
GENESIS_MASTER_HZ = 53_693_175
SOURCE_TIMER_HZ = GENESIS_MASTER_HZ / (7 * 2304 * 28)
SOURCE_PCM_HZ = GENESIS_MASTER_HZ / (7 * 144 * 5)
NES_PHASE_STEP = 64828
FREQUENCY_RANGES = (
    ('fm', 398432, 96, '0c5c595766d0c65c8c41caf264b2393dbb7737dc0aee98dbc98d4fc7cd8e042b'),
    ('psg', 398528, 96, '955d53b9a5877dac5b5798c6252e6f90bc1ad0cd9d888ae718283320c913aaca'),
)
# kind, name, byte offset, length, SHA256; source order is the original ID order.
AUDIO_RANGES = (
    ('bgm', 'stage_1', 312460, 4894, '19b6402e0dc7aad7ccd6d2c1592c960b125e1967c908b45dcb58ff6e7c689e75'),
    ('bgm', 'stage_2', 317354, 5396, '25fea6d587f37c3f4ac31eef70123a6ceda2e11c52337c00d092d014d3a61af8'),
    ('bgm', 'stage_3', 322750, 8018, '02703899b34539dc97ca8ec0ff09ce221978193bd74e14d4ee28dca8176a22ba'),
    ('bgm', 'stage_4', 330768, 2405, 'af823600e9a04c8606eb0c9c0c7f4d77e5ed7a95410ee9355e7b12fd163ca71c'),
    ('bgm', 'stage_5', 333173, 3138, 'aed43131e9945523cbccca7df331c40c9a4077b383703ba462f65d37da671a0d'),
    ('bgm', 'stage_6', 336311, 5936, 'f2e2cbab7981d160fec48c50b28d52eee3dccf7124175f80f593b74e15778313'),
    ('bgm', 'stage_7', 342247, 2602, '734b0363ee54d1eb07e552cf6883a7aaa45a1f00dc5deacef7de27a36bfb38c6'),
    ('bgm', 'boss', 344849, 1450, 'b42c65e3666bacea5728ab9eb0f03fc2dcd9c87115acd9dba2f006b42797dfa5'),
    ('bgm', 'title', 346299, 151, 'c910baea9f2e10f271dc6f04cc3e5c313d4298acc77789b454004ca8e5863e89'),
    ('bgm', 'ending', 346450, 517, '5c67f479565bd8cb8f3436fdc593a0c4260b1906f828b3e360ee0d7a8350e819'),
    ('bgm', 'tally', 346967, 794, '37a77c40165c7879b69b48a7c75ae2bd5389398d2386e33e2ccfefa703151b32'),
    ('bgm', 'game_over', 347761, 232, '6f2c86bf81d119ad0c697ec7a767713caf4d9ae8fe7c662aec975936d757565e'),
    ('bgm', 'continue', 347993, 136, '97f157bf9caba80a9e9d2ef419b88017289e13f9be2ce2f2188f3b9c60a3e1c3'),
    ('sfx', 'type', 348206, 13, 'e98e3ea7594dc412fe19cebb7d824a42115a57b9d431dc0195fbf773abfc341a'),
    ('sfx', 'backspace', 348219, 19, '451c8d5eb818206e99b9e98b7c716aa0cd2694afdb62153809e1a4167dfcc330'),
    ('sfx', 'jump', 348238, 46, '2a1084211c25c7acd6b675bea55cbabd74841ca017ea87489c35ca7ef528eeb2'),
    ('sfx', 'impact', 348284, 13, '8ac16b725ce5fe6030b794bd7a0d8f9e71b73a10e63a34b4eb5fe82133e13b23'),
    ('sfx', 'spring', 348297, 40, 'ef76782cc24514891d7ca23566b07463e99d22bba190156f452e044d7e4f42f3'),
    ('sfx', 'key', 348337, 28, 'd9fe958d752cb67b5ff264fe6bfc1964adcfbdc5c0f2f3586cf2158b5b8e03b9'),
    ('sfx', 'crystal', 348365, 63, '85fadc988c7d6867b430a2b24ed335ebe1d8fe9225852aebef1523180b2f10cb'),
    ('sfx', 'all_key', 348428, 52, 'd1a4bc86cf624d159fac2ae37cf555e3c68a0ff498946d715d2597a3024fa11d'),
    ('sfx', 'all_crystal', 348480, 105, 'c8f215eb6c17d174f279668871a63b73908a69704293b31d89cdd9ea7afb4fdb'),
    ('sfx', 'explosion', 348585, 6, 'fbec935b5f24ff2a4d24fae881db0e3bf6c0845a434c951701a6109043d0252f'),
    ('sfx', 'ouch', 348591, 30, '6b18051c856f57612b643f2854ab0f2fe1698ebab93ae6bf2c9a43e0b8d9e76a'),
    ('sfx', 'ouch_sink', 348621, 86, '1f3b1ae9bac7c68ab92d9760c0b2af27b463ee6d0f838aa62b0cbf189881b110'),
    ('sfx', 'ouch_burn', 348707, 82, '8af61e0592d2f6ab1fc6fd2feef74a3a6ad9edefc6df426312b56789bcc7e937'),
    ('sfx', 'ouch_fall', 348789, 117, 'b899c847e6d18cb9bc9a88386b8eeaa714cfcc4d697f31d2660c2c0e8e241441'),
    ('sfx', 'ouch_shock', 348906, 125, '73104d1492ce10b749249a84cc03e5ae9db8bf051243d91b98f660d1a46cda8f'),
    ('sfx', 'ouch_explosion', 349031, 89, '7fada18c2a1a393f60abde178ee691773a865d037b6fb2eee3ce5ae09fb5e673'),
    ('sfx', '1up', 349120, 126, '782285d828cc5d29955d9ebaa18fdbf24425546bf0604ed86e96e5bcd6de092f'),
    ('sfx', 'goal', 349246, 126, 'afc54861522e7984f7488135f3992984428d91f19c631450543eaa5b8cb19e46'),
    ('sfx', 'pause', 349372, 56, 'c2a0ceb84b0c3c95ee769d7c4049518cc005ee94fd463f019fbf11dfb336cbde'),
)

# id, kind, descriptive name, byte offset, length, SHA256.
INSTRUMENT_RANGES = (
    (0, 'fm', 'bell', 349540, 32, 'f83d969256f49d76d0da87d55fda6fb9def29d40e6e5c1ffedd18cd265e90693'),
    (1, 'fm', 'sawtooth', 349572, 32, '4ed6b7a646b3664e7847f8abc420296549e2425ff89c43d6a4e921dab0b8de0c'),
    (2, 'fm', 'distortion', 349604, 32, 'e68fa903326fcad843e1174f831908112c2371ac7b5fbefcb6f70bca236a370a'),
    (3, 'pcm', 'explosion', 350112, 8608, '09a00389ccbe5f53702ba958966bdb6975ea298a8ebbabbcbefb6123b1b64964'),
    (4, 'psg', 'psg_4', 349636, 8, '310d34503ea6379d7e0391c92ccccccd9ed42d18486b1fd6fd46ee5fc7d9019a'),
    (5, 'pcm', 'snare', 358720, 3360, '60870dcc4e8f0eab74e2b1cef38222a65686c28dff9c411b323eb0f463314319'),
    (6, 'psg', 'psg_6', 349644, 8, '8cbb52db2fb8afde57693cc4ff60b4c18c9431478d1fbfa639ec55afbca67d9f'),
    (7, 'psg', 'psg_7', 349652, 7, '1705846b6dace1c5876f468bd698b21e00d3cf7126fd078d537e56660dd22591'),
    (8, 'fm', 'sax', 349659, 32, '6092bc2f3afcdc545571310c81137186a588abff02b807c2d70255ff77821e1d'),
    (9, 'fm', 'guitar', 349691, 32, '5266ba171a18ebcc6f16e8e21dd7cfef10344cc03d571c02bd20d9be5e5f82b1'),
    (10, 'fm', 'bass', 349723, 32, '8481ac014c7b4f744c3756b215f4e42e6bf568b57fc7c384d9c9af0bfe971130'),
    (11, 'fm', 'synbass', 349755, 32, '443e169b2962f35dd8b33f063eaeb9ff439271f61430899755e03402d2876c63'),
    (12, 'pcm', 'jingle', 362080, 2944, 'fd6e45169f9ab548ef34a5577ea67fd91f3cc9f2b57f61afa6b89be7524d9482'),
    (13, 'pcm', 'kick', 365024, 2400, '7e4d9a350af32ca4fc48d940a6661182fbc1841a87ef28ff9dfcb140cfb109aa'),
    (14, 'psg', 'psg_14', 349787, 8, '460b55f616184f586bb4d3924494369806afaba16b08c46d45fa49ad60dc62fe'),
    (15, 'fm', 'stage1lead', 349795, 32, 'f157e91823ffd12e67d7005fbe52efc1daffcc8326b76b497e3a95f1bf122ef9'),
    (16, 'psg', 'psg_16', 349827, 8, '28437182f4351ad5c3c66f94c08803619c6332e652b1b3a6a7b4ee4ff0974f04'),
    (17, 'fm', 'bell2', 349835, 32, '3e0687ca3167b82dad64131fd8f0231cde76a6e793a8dbbb331870ddedc8c1cb'),
    (18, 'fm', 'church', 349867, 32, '4a6ce98f2d0d6c19950103632348b89567c51a53fd8e18bf2cdb967ad7a4c5ea'),
    (19, 'fm', 'trumpet', 349899, 32, '82226f0744d34bbe320465ce98081daa2dd3ac1d4200846f6c76e4e23d0ce1c9'),
    (20, 'pcm', 'tick', 367424, 1920, 'b45b368823fb5458989962c78297c3fb9a5479f0ba5be981bd48ed49b5f6dc02'),
    (21, 'pcm', 'tock', 369344, 1888, '8b30877cd5710600cd55b625940af2507c29a05ac71d89126eaca3e86a529daa'),
    (22, 'fm', 'impact', 349931, 32, 'f97a0c87ead4e25f586171597e3e7c4350b230acc4be9d903e630c6a952d6531'),
    (23, 'fm', 'neslike1', 349963, 32, 'e797a294cad992de3072ba626bb26763805af84834290c429e7183c73fe6c10d'),
    (24, 'fm', 'slapbass', 349995, 32, '5c4df914a87b33ab39232b09c1a9b72d23ceba876f58f544452cc71052828450'),
    (25, 'fm', 'marimba', 350027, 32, '3e0b0644907015ca81afeb06bfbb650ca36c0a2afe529b67de2510b56829344c'),
    (26, 'fm', 'neslike2', 350059, 32, '48e9a214151a72d614ec74a131d687efb0cff7f88930f44ec41c60f5b16a1086'),
    (27, 'pcm', 'thunder', 371232, 22848, '0f3efc30dd36af56c2551ef6e24e369d88daf6d2129a851b40fbe3f930ec3e6f'),
)

INSTRUMENT_META_FIELDS = ('kind', 'duty', 'attack_ticks', 'decay_ticks', 'sustain',
                          'release_ticks', 'dmc_address', 'dmc_length', 'dmc_rate',
                          'source_pcm_ticks_low', 'source_pcm_ticks_high',
                          'psg_total_level', 'psg_attack_rate', 'psg_sustain_level',
                          'psg_decay_rate', 'psg_sustain_rate', 'psg_release_rate')


class AudioFormatError(ValueError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def decode_sona(data: bytes) -> dict:
    """Decode the complete command profile present in all 32 shipped streams.

    Ticks here are stream ticks. BGM's speed command determines their relation
    to the original Timer-B clock; SFX advances every second Timer-B tick.
    Unsupported VM, substream or direct-chip commands fail closed.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= 65535:
        raise AudioFormatError('invalid Sona stream size')
    index = tick = 0
    events = []
    loop = 0

    def byte():
        nonlocal index
        if index >= len(data):
            raise AudioFormatError('truncated Sona command')
        value = data[index]
        index += 1
        return value

    def pitch():
        first = byte()
        if 0x70 <= first < 0x80 or first >= 0xf0:
            return [first, byte()]
        if 0x60 <= first < 0x70 or 0xe0 <= first < 0xf0:
            raise AudioFormatError('noncanonical pitch encoding')
        return [first]

    channels = {0: 'fm1', 1: 'fm2', 2: 'fm3', 3: 'fm3', 4: 'fm4', 5: 'fm5', 6: 'fm6',
                8: 'psg1', 9: 'psg2', 10: 'psg3', 11: 'noise', 14: 'pcm1', 15: 'pcm2'}
    ended = False
    while index < len(data):
        offset = index
        op = byte()
        category, channel = op >> 4, op & 15
        event = {'offset': offset, 'tick': tick, 'opcode': op}
        if category in (0, 4) and channel in (0,1,2,3,4,5,6,8,9,10,11):
            event.update(kind='instrument' if category == 0 else 'volume', channel=channels[channel], value=byte())
        elif category in (1, 3) and channel in (0,1,2,3,4,5,6,8,9,10,11):
            args = [[byte()]] if channel == 11 else [pitch() for _ in range(4 if channel == 3 else 1)]
            event.update(kind='note_on' if category == 1 else 'pitch', channel=channels[channel], pitches=args)
        elif op in (0x1e, 0x1f):
            event.update(kind='sample_on', channel=channels[channel], value=byte())
        elif category == 2 and channel in channels:
            event.update(kind='note_off', channel=channels[channel])
        elif category == 14 and channel in channels:
            event.update(kind='lock', channel=channels[channel])
        elif 0x50 <= op <= 0x56:
            event.update(kind='pan', channel=channels[channel], value=byte())
        elif 0xd0 <= op <= 0xdf:
            duration = channel + 1
            event.update(kind='delay', duration=duration)
            tick += duration
        elif op == 0xfe:
            duration = byte() or 256
            event.update(kind='delay', duration=duration)
            tick += duration
        elif op == 0xfa:
            event.update(kind='tempo', value=byte())
        elif op == 0xfc:
            loop = index
            event.update(kind='loop_start', target=loop)
        elif op == 0xfd:
            event.update(kind='loop', target=loop)
            ended = True
        elif op == 0xff:
            event.update(kind='stop')
            ended = True
        else:
            raise AudioFormatError(f'unsupported Sona opcode {op:#x} at {offset:#x}')
        event['next_offset'] = index
        events.append(event)
        if ended:
            if index != len(data):
                raise AudioFormatError('bytes follow terminal Sona command')
            break
    if not ended:
        raise AudioFormatError('Sona stream has no loop or stop terminator')
    return {'format': 'fdisbull-audio-events-1', 'source_sha256': _sha(data),
            'source_bytes': len(data), 'events': events, 'stream_ticks': tick,
            'looped': events[-1]['kind'] == 'loop', 'loop_offset': loop,
            'timing': 'Timer B = 53693175/(7*2304*28) Hz; BGM speed/64 times that clock; SFX clock/2'}


def encode_sona(program: dict) -> bytes:
    """Compile a complete parsed audio UIL, checking its byte/flow receipts.

    The encoder consumes the typed events, never an auxiliary retained-byte
    field. Re-decoding checks opcode/kind agreement, event offsets, tick counts,
    control targets, exact extent and the declared source digest.
    """
    if not isinstance(program, dict) or program.get('format') != 'fdisbull-audio-events-1':
        raise AudioFormatError('invalid audio event program')
    events = program.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 65535:
        raise AudioFormatError('invalid audio event extent')
    result = bytearray()

    def integer(value, minimum, maximum):
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise AudioFormatError('audio event field has an invalid integer width')

    integer(program.get('source_bytes'), 1, 65535)
    integer(program.get('stream_ticks'), 0, 0xffffffff)
    integer(program.get('loop_offset'), 0, program['source_bytes'] - 1)
    if not isinstance(program.get('looped'), bool):
        raise AudioFormatError('audio loop flag must be boolean')

    def byte(value):
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
            raise AudioFormatError('audio event field does not fit u8')
        result.append(value)

    for event in events:
        if not isinstance(event, dict):
            raise AudioFormatError('audio events must be objects')
        integer(event.get('offset'), 0, program['source_bytes'] - 1)
        integer(event.get('next_offset'), 1, program['source_bytes'])
        integer(event.get('tick'), 0, 0xffffffff)
        byte(event.get('opcode'))
        kind = event.get('kind')
        if kind in ('loop_start','loop'):
            integer(event.get('target'), 0, program['source_bytes'] - 1)
        if kind == 'delay':
            integer(event.get('duration'), 1, 256)
        if kind in ('instrument','volume','pan','tempo','sample_on'):
            byte(event.get('value'))
        elif kind in ('note_on','pitch'):
            pitches = event.get('pitches')
            if not isinstance(pitches, list) or not 1 <= len(pitches) <= 4:
                raise AudioFormatError('invalid pitch argument list')
            for argument in pitches:
                if not isinstance(argument, list) or not 1 <= len(argument) <= 2:
                    raise AudioFormatError('invalid pitch argument width')
                for value in argument:
                    byte(value)
        elif kind == 'delay' and event['opcode'] == 254:
            duration = event.get('duration')
            if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 256:
                raise AudioFormatError('invalid long delay width')
            byte(duration & 255)
        elif kind not in ('note_off','lock','delay','loop_start','loop','stop'):
            raise AudioFormatError('unknown audio event kind')
        if len(result) > 65535:
            raise AudioFormatError('encoded audio exceeds the source extent limit')
    encoded = bytes(result)
    if decode_sona(encoded) != program:
        raise AudioFormatError('audio event fields, offsets, flow targets or source digest disagree')
    return encoded


def _dpcm(samples: bytes) -> bytes:
    """Resample the original unsigned PCM to rate-9 NES differential samples."""
    rate = 1789772.7272727273 / 160.0
    count = max(1, round(len(samples) * rate / SOURCE_PCM_HZ))
    result = bytearray((count + 7) // 8)
    level = 64
    for output in range(count):
        position = min(len(samples) - 1, output * SOURCE_PCM_HZ / rate)
        lower = int(position)
        fraction = position - lower
        value = samples[lower] * (1 - fraction) + samples[min(lower + 1, len(samples) - 1)] * fraction
        target = round(value * 127 / 254)
        if target >= level:
            result[output // 8] |= 1 << (output & 7)
            level = min(127, level + 2)
        else:
            level = max(0, level - 2)
    # DMC length is register*16+1 bytes. Pad by alternating bits around center.
    length = ((max(1, len(result)) - 1 + 15) // 16) * 16 + 1
    if length > 4081:
        raise AudioFormatError('converted sample exceeds a DMC transfer')
    result.extend(b'\x55' * (length - len(result)))
    return bytes(result)


def period_table(*, triangle=False, frequencies=None, psg=False):
    """Period for each 1/16 semitone, with explicit octave folding at chip limits."""
    result = []
    divider = 32 if triangle else 16
    for pitch in range(96 * 16):
        if frequencies is None:
            frequency = 16.351597831287414 * 2 ** (pitch / (12 * 16))
        elif psg:
            octave = max(0, pitch // 192 - 2)
            divisor = max(1, frequencies[(pitch % 192) // 4] >> octave)
            frequency = GENESIS_MASTER_HZ / (15 * 32 * divisor)
        else:
            fnum = frequencies[(pitch % 192) // 4]
            frequency = fnum * GENESIS_MASTER_HZ * 2 ** (pitch // 192) / (7 * 144 * 2 ** 21)
        period = round(1789772.7272727273 / (divider * frequency)) - 1
        while period > 2047:
            frequency *= 2
            period = round(1789772.7272727273 / (divider * frequency)) - 1
        result.append(max(8 if not triangle else 2, min(2047, period)))
    return result


def recover_audio(rom: bytes) -> dict:
    """Extract all original streams/instruments from the qualified shipped ROM."""
    if not isinstance(rom, bytes) or _sha(rom) != ROM_SHA256:
        raise AudioFormatError('audio profile requires the qualified Miniplanets REV04 ROM')
    tracks = []
    for track_id, (kind, name, offset, length, digest) in enumerate(AUDIO_RANGES):
        data = rom[offset:offset + length]
        if _sha(data) != digest:
            raise AudioFormatError('source audio range changed')
        program = decode_sona(data)
        encoded = encode_sona(program)
        if encoded != data:
            raise AudioFormatError('audio output compiler changed the source stream')
        tracks.append({'track': track_id, 'kind': kind, 'name': name,
                       'source_offset': offset, 'source_length': length, 'source_sha256': digest,
                       'bytes_hex': data.hex(), 'event_program': program,
                       'encoded_sha256': _sha(encoded), 'event_round_trip_identical': True})
    instruments = []
    bank = bytearray()
    for ident, kind, name, offset, length, digest in INSTRUMENT_RANGES:
        data = rom[offset:offset + length]
        if _sha(data) != digest:
            raise AudioFormatError('source instrument range changed')
        meta = [0,2,1,8,12,8,0,0,9,0,0,0,0,0,0,0,0]
        if kind == 'psg':
            meta[0] = 1
            meta[1] = 2
            meta[2] = max(1, (255 - data[0]) // 32 + 1)
            meta[3] = max(1, min(255, 256 // max(1, data[1])))
            meta[4] = min(15, data[2] >> 4)
            meta[5] = max(1, min(255, 256 // max(1, data[5])))
            meta[11:17] = data[:6]
        elif kind == 'pcm':
            if data[-32:] != b'\xff' * 32 or 255 in data[:-32]:
                raise AudioFormatError('invalid original Sona PCM sample')
            sample = _dpcm(data[:-32])
            bank.extend(b'\x55' * ((-len(bank)) % 64))
            if len(bank) + len(sample) > 8192:
                raise AudioFormatError('original percussion does not fit the reserved DMC bank')
            meta[0] = 2
            meta[6] = len(bank) // 64
            meta[7] = (len(sample) - 1) // 16
            ticks = math.ceil((len(data) - 32) * SOURCE_TIMER_HZ / SOURCE_PCM_HZ)
            meta[9], meta[10] = ticks & 255, ticks >> 8
            bank.extend(sample)
        else:
            algorithm = data[0] & 7
            carriers = (3,) if algorithm < 4 else (2,3) if algorithm == 4 else (1,2,3) if algorithm < 7 else (0,1,2,3)
            attack = max(data[9 + operator] & 31 for operator in carriers)
            release = max(data[21 + operator] & 15 for operator in carriers)
            sustain = min(data[21 + operator] >> 4 for operator in carriers)
            meta[1] = 1 if ident == 23 else 0 if ident == 26 else 2
            meta[2] = max(1, (31 - attack) // 4 + 1)
            meta[3] = 8
            meta[4] = max(1, 15 - sustain)
            meta[5] = max(1, (15 - release) * 2 + 1)
        instruments.append({'id': ident, 'kind': kind, 'name': name, 'source_offset': offset,
                            'source_length': length, 'source_sha256': digest, 'nes_meta': meta})
    used = len(bank)
    bank.extend(b'\x55' * (8192 - len(bank)))
    source_frequencies = {}
    frequency_receipts = []
    for kind, offset, length, digest in FREQUENCY_RANGES:
        data = rom[offset:offset + length]
        if _sha(data) != digest:
            raise AudioFormatError('source frequency table changed')
        source_frequencies[kind] = [int.from_bytes(data[i:i + 2], 'little') for i in range(0, length, 2)]
        frequency_receipts.append({'kind': kind, 'source_offset': offset, 'source_length': length,
                                   'source_sha256': digest})
    return {'format': 'fdisbull-audio-uil-1', 'role': 'audio', 'source_sha256': ROM_SHA256,
            'clock_hz': SOURCE_TIMER_HZ, 'sfx_clock_divisor': 2,
            'nes_phase_step': NES_PHASE_STEP, 'nes_phase_modulus': 65536,
            'source_pcm_hz': SOURCE_PCM_HZ, 'tracks': tracks, 'instruments': instruments,
            'instrument_meta_fields': list(INSTRUMENT_META_FIELDS), 'dpcm_bank_hex': bank.hex(),
            'dpcm_used_bytes': used, 'frequency_tables': frequency_receipts,
            'pulse_periods': period_table(frequencies=source_frequencies['fm']),
            'triangle_periods': period_table(triangle=True, frequencies=source_frequencies['fm']),
            'psg_pulse_periods': period_table(psg=True, frequencies=source_frequencies['psg']),
            'psg_triangle_periods': period_table(triangle=True, psg=True, frequencies=source_frequencies['psg']),
            'arrangement': {'policy': 'pulse1 lead, triangle lowest tone, pulse2 round-robin remaining tones, noise, priority PCM',
                            'pcm_policy': 'new music hits replace music tails; effects mask music; simultaneous channel2 wins; no late replay',
                            'pcm_loss_counters': ['audio_pcm_dropped', 'audio_pcm_preempted'],
                            'source_channel_state_retained': True,
                            'limits': ['FM and PSG timbre adapted to NES oscillators',
                                       'more than three simultaneous pitched voices use explicit arpeggiation',
                                       'two original PCM voices share one priority DMC voice',
                                       'pitch outside hardware range folds by octaves',
                                       'source envelopes quantized to 4-bit volume; triangle has fixed amplitude']}}


def pitch_value(argument, previous, *, psg=False):
    """Decode Sona pitch into 1/16-semitone units measured from C0."""
    first = argument[0]
    if first == 0x80:
        return previous
    if first < 0x70:
        value = (((first & 7) + (2 if psg else 0)) * 12 + (first >> 3)) * 16
    elif first < 0x80:
        second = argument[1]
        value = (((second & 7) + (2 if psg else 0)) * 12 + ((second >> 3) & 15)) * 16 + (first & 15)
    elif first < 0xf0:
        distance = ((first & 3) * 12 + ((first >> 3) & 15)) * 16
        value = previous + (-distance if first & 4 else distance)
    else:
        second = argument[1]
        distance = ((second & 7) * 12 + ((second >> 3) & 15)) * 16 + (first & 15)
        value = previous + (-distance if second & 128 else distance)
    return max(0, min(1535, value))


class SonaEngine:
    """Logical source stream timing, independent of which NES voices are audible."""
    def __init__(self, audio):
        self.audio = audio
        self.programs = [{event['offset']: event for event in track['event_program']['events']} for track in audio['tracks']]
        self.clock = self.accumulator = 0
        self.nes_phase = self.nes_clock = self.sfx_phase = 0
        self.speed = 32
        self.streams = [None, None]
        self.events = []
        self.priority = 0
        self.status_busy = False
        self.command_count = self.note_count = self.event_crc = 0

    def request(self, kind, ident):
        if kind == 3 or kind == 1 and ident == 255:
            self.streams = [None, None]
            self.priority = 0
        elif kind == 1 and 1 <= ident <= 13:
            self.streams = [{'track': ident - 1, 'pc': 0, 'loop': 0, 'wait': 1}, None]
            self.accumulator = 0
            self.speed = 32
            self.priority = 0
        elif kind == 2 and 1 <= ident <= 19:
            # The shipped driver accepts priority0 too, unlike an API comment.
            priority = (ident - 1) * 4
            if self.streams[1] is not None and priority < self.priority:
                return
            self.priority = priority
            self.streams[1] = {'track': ident + 12, 'pc': 0, 'loop': 0, 'wait': 1}

    @property
    def busy(self):
        return self.status_busy

    def _step(self, slot):
        stream = self.streams[slot]
        if stream is None:
            return
        stream['wait'] -= 1
        if stream['wait']:
            return
        for _ in range(2048):
            event = self.programs[stream['track']].get(stream['pc'])
            if event is None:
                raise AudioFormatError('stream PC is not an event boundary')
            stream['pc'] = event['next_offset']
            kind = event['kind']
            self.command_count = (self.command_count + 1) & 65535
            self.event_crc = ((self.event_crc << 1) ^ event['opcode'] ^ (event['offset'] + 1)) & 65535
            if kind == 'note_on':
                self.note_count = (self.note_count + 1) & 65535
            self.events.append({'clock': self.clock, 'slot': slot, 'track': stream['track'], **event})
            if kind == 'delay':
                stream['wait'] = event['duration']
                return
            if kind == 'stop':
                self.streams[slot] = None
                if slot:
                    self.priority = 0
                return
            if kind == 'loop':
                stream['pc'] = stream['loop']
            if kind == 'loop_start':
                stream['loop'] = event['target']
            if kind == 'tempo':
                self.speed = event['value']
        raise AudioFormatError('non-progressing source audio loop')

    def tick(self):
        self.clock += 1
        self.accumulator += self.speed * 4
        while self.accumulator >= 256:
            self.accumulator -= 256
            self._step(0)
        self.sfx_phase ^= 1
        if not self.sfx_phase:
            self._step(1)
            self.status_busy = self.streams[1] is not None

    def nes_tick(self):
        """One of the two NES interrupts per frame, corrected to source tempo."""
        self.nes_clock += 1
        self.nes_phase += NES_PHASE_STEP
        if self.nes_phase >= 65536:
            self.nes_phase -= 65536
            self.tick()
