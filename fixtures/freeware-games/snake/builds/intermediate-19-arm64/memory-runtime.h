#ifndef FDISBULL_MEMORY_RUNTIME_1
#define FDISBULL_MEMORY_RUNTIME_1
#include <stddef.h>
#include <stdint.h>
size_t fdb_word_count(void);
const uint32_t *fdb_words(void);
int fdb_copy_words(uint32_t *, size_t);
int fdb_function_index(const char *);
int fdb_call(size_t, const uint32_t *, const uint32_t *, size_t, int);
int fdb_dispatch(const uint32_t *, const uint32_t *, size_t, int);
int fdb_initialize(uint32_t);
int fdb_select_region(size_t, size_t);
int fdb_selected_region(size_t);
int fdb_replace_words(const uint32_t *, size_t);
uint64_t fdb_revision(void);
uint64_t fdb_invocation_count(size_t);
uint64_t fdb_region_invocation_count(size_t, size_t);
uint32_t fdb_last_steps(void);
const char *fdb_last_error(void);
const char *fdb_config_sha256(void);
void fdb_close(void);
int fdb_closed(void);
#endif
