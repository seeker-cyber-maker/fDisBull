/* Authored standalone checkpoint/corruption witness, not a fidelity oracle.
 * Link the accepted fmopl object; never recompile or edit the synthesizer. */
#include "qemu/osdep.h"
#include "hw/audio/fmopl.h"

#define FUTURE_FRAMES (777 + 1001 + 509)

typedef struct TimerWitness {
    unsigned calls;
    unsigned seen;
} TimerWitness;

static void require(bool value, const char *message)
{
    if (!value) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static void timer_event(void *opaque, int channel, double interval)
{
    TimerWitness *w = opaque;
    require(channel >= 0 && channel < 2 && interval >= 0,
            "invalid timer callback");
    w->calls++;
    w->seen |= 1u << channel;
}

static FM_OPL *create(TimerWitness *w)
{
    FM_OPL *o = OPLCreate(3579545, 32000);
    require(o != NULL, "OPLCreate");
    OPLSetCheckpointMode(o);
    OPLSetTimerHandler(o, timer_event, w);
    return o;
}

static void reg(FM_OPL *o, unsigned address, unsigned value)
{
    OPLWrite(o, 0, address);
    OPLWrite(o, 1, value);
}

static void configure(FM_OPL *o)
{
    static const unsigned offsets[9] = {0, 1, 2, 8, 9, 10, 16, 17, 18};
    unsigned c, n;
    int16_t warmup[513];

    reg(o, 1, 0x20);
    for (c = 0; c < 9; c++) {
        for (n = 0; n < 2; n++) {
            unsigned offset = offsets[c] + 3 * n;
            reg(o, 0x20 + offset, 0xe1); /* AM/VIB/sustain/multiplier. */
            reg(o, 0x40 + offset, n ? 0 : 0x10);
            reg(o, 0x60 + offset, 0x83 + ((c % 5) << 4));
            reg(o, 0x80 + offset, 0x35);
            reg(o, 0xe0 + offset, (c + n) % 4);
        }
        reg(o, 0xc0 + c, 0x0e | (c & 1));
        reg(o, 0xa0 + c, 0x80 + c * 7);
        reg(o, 0xb0 + c, 0x32);
    }
    reg(o, 0xbd, 0x3f); /* Five drums, initially shallow LFO tables. */
    reg(o, 2, 0xf0);
    reg(o, 3, 0xc0);
    reg(o, 4, 3);
    YM3812UpdateOne(o, warmup, ARRAY_SIZE(warmup));
    /* The accepted model caches the global LFO selectors at rendering.
     * A later BD write changes chip selectors without changing that cache. */
    reg(o, 0xbd, 0xff);
    OPLWrite(o, 0, 0xa4); /* Pending address: future begins with DATA only. */
}

static void get(FM_OPL *o, OPLCheckpointState *s)
{
    require(OPLCheckpointGet(o, s), "OPLCheckpointGet");
}

static void assert_coverage(const OPLCheckpointState *s)
{
    unsigned c, n, active = 0;
    require(s->address == 0xa4 && s->rhythm == 0x3f && s->st0 && s->st1,
            "pending address/rhythm/timer coverage");
    require(s->cache_ready && s->ams_depth == 1 && s->vib_depth == 1 &&
            s->cache_ams_depth == 0 && s->cache_vib_depth == 0,
            "cached and per-chip LFO selectors must differ");
    for (c = 0; c < 9; c++) {
        require(s->channel[c].keyon == 1, "all nine channels keyed on");
        for (n = 0; n < 2; n++) {
            active += s->channel[c].slot[n].evc < (8192u << 16);
        }
    }
    require(active == 18 && s->noise != 0x6d2b79f5,
            "all operators active and private rhythm noise advanced");
}

static void future(FM_OPL *o, TimerWitness *w, int16_t *pcm,
                   OPLCheckpointState *final)
{
    unsigned before = w->calls;
    OPLCheckpointState pending;
    OPLWrite(o, 1, 0x5a);
    get(o, &pending);
    require(pending.address == 0xa4 && pending.registers[0xa4] == 0x5a,
            "restored pending address did not receive DATA-only write");
    YM3812UpdateOne(o, pcm, 777);
    reg(o, 0xb2, 0x12); /* Release one channel after the captured frontier. */
    OPLTimerOver(o, 0);
    YM3812UpdateOne(o, pcm + 777, 1001);
    reg(o, 0xbd, 0x3f);
    OPLTimerOver(o, 1);
    YM3812UpdateOne(o, pcm + 1778, 509);
    get(o, final);
    require(w->calls - before == 2 && (w->seen & 3) == 3,
            "timer callbacks must be fresh, not replayed during import");
}

static unsigned rejected_states(FM_OPL *o, TimerWitness *w,
                                const OPLCheckpointState *saved)
{
    OPLCheckpointState bad, before, after;
    unsigned i;
    get(o, &before);
    for (i = 0; i < 18; i++) {
        unsigned calls_before = w->calls, seen_before = w->seen;
        bad = *saved;
        switch (i) {
        case 0: bad.channel[0].slot[0].ar_index = 16; break;
        case 1: bad.channel[0].slot[0].dr_index = 16; break;
        case 2: bad.channel[0].slot[0].rr_index = 16; break;
        case 3: bad.channel[0].slot[0].wave_index = 4; break;
        case 4: bad.rate = 44100; break;
        case 5: bad.clock++; break;
        case 6: bad.channel[0].slot[0].evc = (8192u << 16) + 1; break;
        case 7: bad.channel[0].slot[0].evs = 4096u << 16; break;
        case 8: bad.channel[0].slot[0].ksl = 32; break;
        case 9: bad.channel[0].slot[0].KSR = 3; break;
        case 10: bad.channel[0].slot[0].TL = 2017; break;
        case 11: bad.cache_ams_depth = 2; break;
        case 12: bad.cache_ready = 2; break;
        case 13: bad.noise = 0; break;
        case 14: bad.T0 = 0; break;
        case 15: bad.T1 = 17; break;
        case 16: bad.channel[0].CON = 2; break;
        default: bad.channel[0].op1_out0 = INT32_MAX; break;
        }
        require(!OPLCheckpointValidate(o, &bad), "malformed state validated");
        require(!OPLCheckpointPut(o, &bad), "malformed state imported");
        get(o, &after);
        require(w->calls == calls_before && w->seen == seen_before,
                "failed validation/import invoked timer callbacks");
        require(!memcmp(&before, &after, sizeof(after)),
                "failed import changed synthesizer/cache/register state");
    }
    return i;
}

static FILE *open_file(const char *directory, const char *name, const char *mode)
{
    g_autofree char *path = g_build_filename(directory, name, NULL);
    FILE *f = fopen(path, mode);
    require(f != NULL, "cannot open harness artifact");
    return f;
}

static void put32(FILE *f, uint32_t v)
{
    unsigned char bytes[4] = {v, v >> 8, v >> 16, v >> 24};
    require(fwrite(bytes, 1, 4, f) == 4, "write LE word");
}

static uint32_t get32(FILE *f)
{
    unsigned char b[4];
    require(fread(b, 1, 4, f) == 4, "read LE word");
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) |
           ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}

static void state_file(const char *directory, const char *name,
                       OPLCheckpointState *state, bool write)
{
    FILE *f = open_file(directory, name, write ? "wbx" : "rb");
    size_t i, prefix = offsetof(OPLCheckpointState, registers);
    unsigned char magic[8];
    require(prefix % 4 == 0 && prefix + 256 == sizeof(*state),
            "unexpected scalar-wire layout");
    if (write) {
        require(fwrite("FDBOPL01", 1, 8, f) == 8, "write state magic");
        put32(f, 1); put32(f, sizeof(*state));
    } else {
        require(fread(magic, 1, 8, f) == 8 && !memcmp(magic, "FDBOPL01", 8) &&
                get32(f) == 1 && get32(f) == sizeof(*state), "state header");
        memset(state, 0, sizeof(*state));
    }
    for (i = 0; i < prefix; i += 4) {
        uint32_t value;
        if (write) {
            memcpy(&value, (unsigned char *)state + i, 4); put32(f, value);
        } else {
            value = get32(f); memcpy((unsigned char *)state + i, &value, 4);
        }
    }
    if (write) {
        require(fwrite(state->registers, 1, 256, f) == 256, "write registers");
    } else {
        require(fread(state->registers, 1, 256, f) == 256 && fgetc(f) == EOF,
                "noncanonical state length");
    }
    require(fclose(f) == 0, "close state artifact");
}

static void pcm_file(const char *directory, const char *name,
                     int16_t *pcm, bool write)
{
    FILE *f = open_file(directory, name, write ? "wbx" : "rb");
    unsigned i;
    for (i = 0; i < FUTURE_FRAMES; i++) {
        unsigned char b[2];
        if (write) {
            uint16_t value = pcm[i]; b[0] = value; b[1] = value >> 8;
            require(fwrite(b, 1, 2, f) == 2, "write PCM");
        } else {
            require(fread(b, 1, 2, f) == 2, "read PCM");
            pcm[i] = (int16_t)((uint16_t)b[0] | ((uint16_t)b[1] << 8));
        }
    }
    if (!write) require(fgetc(f) == EOF, "noncanonical PCM length");
    require(fclose(f) == 0, "close PCM artifact");
}

int main(int argc, char **argv)
{
    TimerWitness witness = {0};
    FM_OPL *o;
    OPLCheckpointState captured, final, actual;
    int16_t expected_pcm[FUTURE_FRAMES], actual_pcm[FUTURE_FRAMES];
    unsigned rejected, calls;
    bool hot;
    require(argc == 3, "usage: harness hot|cold new-output-directory");
    hot = !strcmp(argv[1], "hot");
    require(hot || !strcmp(argv[1], "cold"), "unknown mode");
    o = create(&witness);
    if (hot) {
        configure(o); get(o, &captured); assert_coverage(&captured);
        state_file(argv[2], "captured.state", &captured, true);
        rejected = rejected_states(o, &witness, &captured);
        future(o, &witness, expected_pcm, &final);
        pcm_file(argv[2], "expected.pcm", expected_pcm, true);
        state_file(argv[2], "expected-final.state", &final, true);
    } else {
        state_file(argv[2], "captured.state", &captured, false);
        state_file(argv[2], "expected-final.state", &final, false);
        pcm_file(argv[2], "expected.pcm", expected_pcm, false);
        assert_coverage(&captured);
        rejected = rejected_states(o, &witness, &captured);
    }
    calls = witness.calls;
    require(OPLCheckpointPut(o, &captured), "restore rejected captured state");
    require(witness.calls == calls, "restore invoked timer callbacks");
    get(o, &actual);
    require(!memcmp(&actual, &captured, sizeof(actual)), "immediate restored state differs");
    future(o, &witness, actual_pcm, &actual);
    require(!memcmp(expected_pcm, actual_pcm, sizeof(actual_pcm)), "future PCM differs");
    require(!memcmp(&final, &actual, sizeof(actual)), "future synth state differs");
    require(actual.noise != captured.noise, "future did not exercise rhythm noise");
    {
        unsigned i;
        bool varying = false;
        for (i = 1; i < FUTURE_FRAMES; i++) varying |= actual_pcm[i] != actual_pcm[0];
        require(varying, "synth future was constant");
    }
    pcm_file(argv[2], hot ? "hot.pcm" : "cold.pcm", actual_pcm, true);
    state_file(argv[2], hot ? "hot-final.state" : "cold-final.state", &actual, true);
    OPLDestroy(o);
    printf("{\"passed\":true,\"mode\":\"%s\",\"pid\":%ld,"
           "\"future_frames\":%u,\"active_channels\":9,\"active_operators\":18,"
           "\"corrupt_states_rejected_atomically\":%u,\"cached_depth_divergence\":true,"
           "\"pending_data_only_write\":true,\"pointer_free\":true,"
           "\"fidelity_oracle\":false}\n", argv[1], (long)getpid(), FUTURE_FRAMES, rejected);
    return 0;
}
