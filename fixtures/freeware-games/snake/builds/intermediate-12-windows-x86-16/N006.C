#include "M16ABI.H"
#pragma code_seg("FDBN6")
FdbBlockResult fdb16_n6(Fdb16Arena *fdb_words) {
  FdbU32 fdb_remaining;
  FdbU32 fdb_failed;
  FdbBlockResult fdb_result;
  FdbU32 fdb_t0;
  FdbU32 fdb_t1;
  FdbU32 fdb_t2;
  FdbU32 fdb_t3;
  FdbU32 fdb_t4;
  fdb_remaining = 1UL;
  fdb_failed = 0UL;
  fdb_result.status = 1UL; fdb_result.steps = 0UL; fdb_result.cut = 0UL;
  if (!fdb_words || fdb16_word_count(fdb_words) != 70000UL) return fdb_result;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,606UL,&fdb_t0)) { fdb_failed = 2UL; goto fdb_done; }
  fdb_t1 = (FdbU32)(fdb_t0 * 25173UL);
  fdb_t2 = (FdbU32)(fdb_t1 + 13849UL);
  fdb_t3 = (FdbU32)(fdb_t2 & 65535UL);
  fdb_t4 = (FdbU32)(fdb_t3 & 65535UL);
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,606UL,fdb_t4)) { fdb_failed = 2UL; goto fdb_done; }
fdb_done:
  fdb_result.status = fdb_failed;
  fdb_result.steps = 1UL-fdb_remaining;
  fdb_result.cut = 0UL;
  return fdb_result;
}
