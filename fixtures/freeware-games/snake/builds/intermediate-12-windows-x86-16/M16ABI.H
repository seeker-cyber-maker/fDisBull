#ifndef FDISBULL_WIN16_MEMORY_ABI_1
#define FDISBULL_WIN16_MEMORY_ABI_1
#include <limits.h>
#if ULONG_MAX == 4294967295UL
typedef unsigned long FdbU32;
#elif UINT_MAX == 4294967295UL
typedef unsigned int FdbU32;
#else
#error No exact unsigned 32-bit carrier is available
#endif
typedef unsigned short FdbU16;
typedef char FdbU16_must_be_two_bytes[(sizeof(FdbU16)==2)?1:-1];
typedef char FdbU32_must_be_four_bytes[(sizeof(FdbU32)==4)?1:-1];
typedef struct Fdb16Arena Fdb16Arena;
typedef struct { FdbU32 status, steps, cut; } FdbBlockResult;
FdbU32 fdb16_word_count(const Fdb16Arena *);
int fdb16_read(const Fdb16Arena *, FdbU32, FdbU32 *);
int fdb16_write(Fdb16Arena *, FdbU32, FdbU32);
Fdb16Arena *fdb16_clone(const Fdb16Arena *);
int fdb16_copy(Fdb16Arena *, const Fdb16Arena *);
void fdb16_release(Fdb16Arena *);
#endif
