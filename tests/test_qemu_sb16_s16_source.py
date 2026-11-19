"""Execute the recovered C admission helpers with independent boundary inputs.

These are source probes, not QEMU/device persistence qualification. The small C
types below model the fields read by the two helpers; real DMA ownership, voice
reconstruction, PCM futures and process cleanup need the native guest tests.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

import pytest


PACKAGE = Path(__file__).resolve().parents[1] / 'native/qemu-sb16-s16-checkpoint'


@pytest.fixture(scope='module')
def s16_source_probe(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler required for the S16 source probes')
    manifest = json.loads((PACKAGE / 'source-manifest.json').read_text())
    patch = (PACKAGE / manifest['patch']['file']).read_bytes()
    assert len(patch) == manifest['patch']['bytes']
    assert hashlib.sha256(patch).hexdigest() == manifest['patch']['sha256']
    additions = ''.join(line[1:] for line in patch.decode().splitlines(keepends=True)
                        if line.startswith('+') and not line.startswith('+++'))
    helpers = []
    for name in ('sb16_checkpoint_voice_format', 'sb16_checkpoint_s16_dma_safe'):
        start = additions.index(f'static bool {name}(')
        end = additions.index('\n}\n', start) + 3
        helpers.append(additions[start:end])
    directory = tmp_path_factory.mktemp('sb16-s16-source')
    source = directory / 'probe.c'
    source.write_text(_PREFIX + '\n'.join(helpers) + _CASES)
    binary = directory / 'probe'
    result = subprocess.run(
        [compiler, '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
         str(source), '-o', str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


_PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Symbolic enum values are local to this source probe, not a wire codec. */
enum { AUDIO_FORMAT_U8 = 0, AUDIO_FORMAT_S16 = 3 };
typedef struct PCMInfo {
    int bits, is_signed, nchannels, freq;
} PCMInfo;
typedef struct SWVoiceOut { PCMInfo info; } SWVoiceOut;
typedef struct I8257Regs {
    uint16_t base[2];
    int now[2], mode;
} I8257Regs;
typedef struct I8257State {
    I8257Regs regs[4];
    int dshift;
    int owner_channel;
} I8257State;
typedef struct SB16State {
    I8257State *isa_hdma;
    SWVoiceOut *voice;
    int hdma, use_hdma, fmt_bits, fmt_signed, fmt, fmt_stereo;
    int align, bytes_per_second, block_size, left_till_irq, dma_auto, fifo;
} SB16State;
#define I8257(d) (d)
static bool fdisbull_sb16_dma_channel(I8257State *d, int channel)
{
    return d->owner_channel == channel;
}
'''


_CASES = r'''
static I8257State high;
static SWVoiceOut voice;

static SB16State valid(int channels)
{
    SB16State s;
    memset(&s, 0, sizeof(s));
    memset(&high, 0, sizeof(high));
    memset(&voice, 0, sizeof(voice));
    high.dshift = 1;
    high.owner_channel = 5;
    high.regs[1].base[1] = 2047; /* 2048 controller words = 4096 bytes. */
    high.regs[1].now[0] = 0x2000;
    high.regs[1].now[1] = 64;
    high.regs[1].mode = 0x49; /* Single/increment/memory-to-device/channel1. */
    voice.info = (PCMInfo){ .bits=16, .is_signed=1, .nchannels=channels,
                            .freq=11025 };
    s.isa_hdma = &high;
    s.voice = &voice;
    s.hdma = 5;
    s.use_hdma = 1;
    s.fmt_bits = 16;
    s.fmt_signed = 1;
    s.fmt = AUDIO_FORMAT_S16;
    s.fmt_stereo = channels - 1;
    s.align = 2 * channels - 1;
    s.bytes_per_second = 11025 * 2 * channels;
    s.block_size = 1024;
    s.left_till_irq = 256;
    return s;
}

static void rejected(SB16State *s)
{
    assert(!sb16_checkpoint_s16_dma_safe(s));
}

int main(int argc, char **argv)
{
    SB16State s;
    int32_t format;
    assert(argc == 2);
    if (!strcmp(argv[1], "voice_formats")) {
        s = valid(1);
        format = -1;
        assert(sb16_checkpoint_voice_format(NULL, &format));
        assert(format == AUDIO_FORMAT_U8);
        voice.info.bits = 8;
        voice.info.is_signed = 0;
        assert(sb16_checkpoint_voice_format(&voice, &format));
        assert(format == AUDIO_FORMAT_U8);
        voice.info.bits = 16;
        voice.info.is_signed = 1;
        assert(sb16_checkpoint_voice_format(&voice, &format));
        assert(format == AUDIO_FORMAT_S16);
    } else if (!strcmp(argv[1], "unsupported_formats")) {
        const int widths[] = { 0, 8, 16, 24, 32, 64 };
        const int signs[] = { -1, 0, 1, 2 };
        (void)valid(1);
        for (unsigned i=0; i<sizeof(widths)/sizeof(widths[0]); i++) {
            for (unsigned j=0; j<sizeof(signs)/sizeof(signs[0]); j++) {
                int bits=widths[i], sign=signs[j];
                voice.info.bits=bits; voice.info.is_signed=sign;
                if ((bits==8 && sign==0) || (bits==16 && sign==1))
                    continue;
                format=123;
                assert(!sb16_checkpoint_voice_format(&voice, &format));
                assert(format==123); /* Failure must not invent a format. */
            }
        }
    } else if (!strcmp(argv[1], "complete_frames")) {
        const int rates[] = { 5000, 11025, 45000 };
        for (int channels=1; channels<=2; channels++) {
            for (int fifo=0; fifo<=1; fifo++) {
                for (int automatic=0; automatic<=1; automatic++) {
                    for (unsigned i=0; i<sizeof(rates)/sizeof(rates[0]); i++) {
                        s=valid(channels); s.fifo=fifo; s.dma_auto=automatic;
                        voice.info.freq=rates[i];
                        s.bytes_per_second=rates[i]*2*channels;
                        high.regs[1].mode |= automatic ? 0x10 : 0;
                        assert(sb16_checkpoint_s16_dma_safe(&s));
                    }
                }
            }
        }
    } else if (!strcmp(argv[1], "word_addresses")) {
        const int admitted[] = { 0, 2, 131070 };
        const int refused[] = { -2, -1, 1, 131071, 131072 };
        for (int channels=1; channels<=2; channels++) {
            s=valid(channels);
            for (unsigned i=0; i<sizeof(admitted)/sizeof(admitted[0]); i++) {
                high.regs[1].now[0]=admitted[i];
                assert(sb16_checkpoint_s16_dma_safe(&s));
            }
            for (unsigned i=0; i<sizeof(refused)/sizeof(refused[0]); i++) {
                high.regs[1].now[0]=refused[i]; rejected(&s);
            }
        }
    } else if (!strcmp(argv[1], "word_capacity")) {
        s=valid(1);
        high.regs[1].base[1]=0; /* One word: exactly one mono S16 frame. */
        high.regs[1].now[1]=0;
        s.block_size=s.left_till_irq=2;
        assert(sb16_checkpoint_s16_dma_safe(&s));
        s=valid(2);
        high.regs[1].base[1]=0;
        high.regs[1].now[1]=0;
        s.block_size=s.left_till_irq=4;
        rejected(&s); /* A stereo frame needs two words. */
        high.regs[1].base[1]=1;
        assert(sb16_checkpoint_s16_dma_safe(&s));
        high.regs[1].base[1]=65535;
        s.block_size=s.left_till_irq=131072;
        assert(sb16_checkpoint_s16_dma_safe(&s));
    } else if (!strcmp(argv[1], "byte_cursor")) {
        for (int channels=1; channels<=2; channels++) {
            s=valid(channels);
            high.regs[1].now[1]=0;
            assert(sb16_checkpoint_s16_dma_safe(&s));
            high.regs[1].now[1]=4096-2*channels;
            assert(sb16_checkpoint_s16_dma_safe(&s));
            high.regs[1].now[1]=-1; rejected(&s);
            high.regs[1].now[1]=4096; rejected(&s);
            high.regs[1].now[1]=4097; rejected(&s);
            high.regs[1].now[1]=1; rejected(&s);
        }
        s=valid(2); high.regs[1].now[1]=2; rejected(&s);
        s=valid(1); high.regs[1].now[1]=2;
        assert(sb16_checkpoint_s16_dma_safe(&s));
    } else if (!strcmp(argv[1], "dma_owner")) {
        s=valid(1); s.use_hdma=0; rejected(&s);
        s=valid(1); high.dshift=0; rejected(&s);
        s=valid(1); high.dshift=2; rejected(&s);
        s=valid(1); high.owner_channel=6; rejected(&s);
        for (int channel=0; channel<8; channel++) {
            if (channel==5) continue;
            s=valid(1); s.hdma=channel; rejected(&s);
        }
    } else if (!strcmp(argv[1], "dma_mode")) {
        s=valid(1); high.regs[1].mode|=0x20; rejected(&s);
        s=valid(1); high.regs[1].mode=0x45; rejected(&s);
        s=valid(1); high.regs[1].mode=0x41; rejected(&s);
        s=valid(1); high.regs[1].mode=0x4d; rejected(&s);
    } else if (!strcmp(argv[1], "dsp_voice_agreement")) {
        s=valid(1); s.fmt_bits=8; rejected(&s);
        s=valid(1); s.fmt_signed=0; rejected(&s);
        s=valid(1); s.fmt=AUDIO_FORMAT_U8; rejected(&s);
        s=valid(1); s.fmt_stereo=1; rejected(&s);
        s=valid(2); s.fmt_stereo=0; rejected(&s);
        s=valid(1); s.align=0; rejected(&s);
        s=valid(2); s.align=1; rejected(&s);
        s=valid(1); s.bytes_per_second=11025; rejected(&s);
        s=valid(2); s.bytes_per_second=22050; rejected(&s);
        s=valid(1); voice.info.freq=22050; rejected(&s);
    } else if (!strcmp(argv[1], "block_and_irq_credit")) {
        const int bad_block[] = { -4, 0, 1, 131073, 131074 };
        const int bad_credit[] = { -4, 0, 1, 1025, 1026 };
        for (int channels=1; channels<=2; channels++) {
            for (unsigned i=0; i<sizeof(bad_block)/sizeof(bad_block[0]); i++) {
                s=valid(channels); s.block_size=bad_block[i]; rejected(&s);
            }
            for (unsigned i=0; i<sizeof(bad_credit)/sizeof(bad_credit[0]); i++) {
                s=valid(channels); s.left_till_irq=bad_credit[i]; rejected(&s);
            }
            s=valid(channels); s.left_till_irq=s.block_size;
            assert(sb16_checkpoint_s16_dma_safe(&s));
        }
        s=valid(2); s.block_size=1026; rejected(&s);
        s=valid(2); s.left_till_irq=254; rejected(&s);
        s=valid(1); s.block_size=1026; s.left_till_irq=254;
        assert(sb16_checkpoint_s16_dma_safe(&s));
    } else if (!strcmp(argv[1], "boolean_controls")) {
        const int invalid[] = { -1, 2 };
        for (unsigned i=0; i<sizeof(invalid)/sizeof(invalid[0]); i++) {
            s=valid(1); s.fifo=invalid[i]; rejected(&s);
            s=valid(2); s.dma_auto=invalid[i]; rejected(&s);
        }
    } else if (!strcmp(argv[1], "stationary_probe")) {
        SB16State saved;
        I8257State saved_high;
        SWVoiceOut saved_voice;
        for (int channels=1; channels<=2; channels++) {
            s=valid(channels);
            saved=s; saved_high=high; saved_voice=voice;
            assert(sb16_checkpoint_s16_dma_safe(&s));
            assert(!memcmp(&saved,&s,sizeof(s)));
            assert(!memcmp(&saved_high,&high,sizeof(high)));
            assert(!memcmp(&saved_voice,&voice,sizeof(voice)));
            high.regs[1].now[1]=1;
            saved_high=high;
            rejected(&s);
            assert(!memcmp(&saved,&s,sizeof(s)));
            assert(!memcmp(&saved_high,&high,sizeof(high)));
            assert(!memcmp(&saved_voice,&voice,sizeof(voice)));
        }
    } else {
        return 2;
    }
    puts("S16 source contract passed");
    return 0;
}
'''


@pytest.mark.parametrize('case', [
    'voice_formats', 'unsupported_formats', 'complete_frames', 'word_addresses',
    'word_capacity', 'byte_cursor', 'dma_owner', 'dma_mode',
    'dsp_voice_agreement', 'block_and_irq_credit', 'boolean_controls',
    'stationary_probe',
])
def test_actual_s16_admission_helpers(s16_source_probe, case):
    result = subprocess.run([str(s16_source_probe), case], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == 'S16 source contract passed\n'
