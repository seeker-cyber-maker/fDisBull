/* Authored 68000 adapter to the reviewed Sona routines retained at their
 * original addresses in the private source-ROM region. No original audio
 * bytes are stored here; BGM/SFX/instrument pointers resolve in that region.
 */
#ifndef FDISBULL_GENESIS_AUDIO_HOST
#include "game_api.h"
#else
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long u32;
#endif

#define SONA_BGM_LIST       0x04c458UL
#define SONA_SFX_LIST       0x054fe2UL
#define SONA_INSTRUMENTS    0x0554f4UL
#define SONA_INSTRUMENT_COUNT 28
#define SONA_STATUS_SFX1    (1U << 5)

extern void genesis_sona_init(void);
extern void genesis_sona_play_bgm(const u8 *stream,
                                  const u8 *instruments,
                                  u8 instrument_count);
extern void genesis_sona_play_sfx(const u8 *stream,
                                  const u8 *instruments,
                                  u8 instrument_count,
                                  u8 priority);
extern void genesis_sona_stop_all(void);
extern u16 genesis_sona_get_status(void);

#ifdef FDISBULL_GENESIS_AUDIO_HOST
extern const u8 *fdisbull_audio_test_stream(u8 kind, u8 id);
extern void fdisbull_audio_test_record(u8 operation, u32 first,
                                      u32 second, u16 third, u16 fourth);
#define AUDIO_SONA_INIT() fdisbull_audio_test_record(0,0,0,0,0)
#define AUDIO_SONA_BGM(stream,instruments,count) \
    fdisbull_audio_test_record(1,(u32)(stream),(u32)(instruments),(u16)(count),0)
#define AUDIO_SONA_SFX(stream,instruments,count,priority) \
    fdisbull_audio_test_record(2,(u32)(stream),(u32)(instruments),(u16)(count),(u16)(priority))
#define AUDIO_SONA_STOP() fdisbull_audio_test_record(3,0,0,0,0)
#define AUDIO_SONA_STATUS() ((u16)fdisbull_audio_test_status())
extern u16 fdisbull_audio_test_status(void);
#else
#define AUDIO_SONA_INIT() genesis_sona_init()
#define AUDIO_SONA_BGM(s,i,n) genesis_sona_play_bgm((s),(i),(n))
#define AUDIO_SONA_SFX(s,i,n,p) genesis_sona_play_sfx((s),(i),(n),(p))
#define AUDIO_SONA_STOP() genesis_sona_stop_all()
#define AUDIO_SONA_STATUS() genesis_sona_get_status()
#endif

static const u8 *sona_stream(u32 table_address, u8 id)
{
#ifdef FDISBULL_GENESIS_AUDIO_HOST
    (void)table_address;
    return fdisbull_audio_test_stream(table_address == SONA_BGM_LIST ? 1 : 2,
                                      id);
#else
    const u32 *table;
    table = (const u32 *)table_address;
    return (const u8 *)table[(u16)(id - 1)];
#endif
}

void audio_init(void)
{
    AUDIO_SONA_INIT();
}

/* kind 1 requests BGM, kind 2 requests SFX, and kind 3 stops all playback.
 * Sona itself owns the YM2612 Timer-B service and PCM Timer-A stream.
 */
void audio_request(u8 kind, u8 id)
{
    const u8 *stream;
    const u8 *instruments;
    u8 priority;

    if (kind == 3 || (kind == 1 && id == 255)) {
        AUDIO_SONA_STOP();
        return;
    }

    instruments = (const u8 *)SONA_INSTRUMENTS;
    if (kind == 1 && id >= 1 && id <= 13) {
        stream = sona_stream(SONA_BGM_LIST, id);
        AUDIO_SONA_BGM(stream, instruments, SONA_INSTRUMENT_COUNT);
    } else if (kind == 2 && id >= 1 && id <= 19) {
        stream = sona_stream(SONA_SFX_LIST, id);
        priority = (u8)((id - 1) * 4);
        AUDIO_SONA_SFX(stream, instruments, SONA_INSTRUMENT_COUNT, priority);
    }
}

/* The 68000 does not clock Sona streams; the original Z80 driver polls the
 * YM2612 Timer-B flag itself and services PCM from Timer A.
 */
void audio_tick(void)
{
}

/* Match the original UpdateSound contract: only SFX stream #1 controls when
 * CurrentSFX is cleared. BGM/PCM activity does not make this status busy.
 */
u8 audio_busy(void)
{
    return (AUDIO_SONA_STATUS() & SONA_STATUS_SFX1) != 0;
}
