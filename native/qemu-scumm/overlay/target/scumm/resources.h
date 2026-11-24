/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FDB_SCUMM_RESOURCES_H
#define FDB_SCUMM_RESOURCES_H

#include "qemu/typedefs.h"
#include "early.h"

/* Immutable decoded bytes; runtime residency and locks live in ScummRuntime.
 * These digests bind data identity. They do not authenticate a publisher. */
typedef struct ScummResourceBank {
    char manifest_sha256[65];
    char source_receipt_sha256[65];
    uint8_t *bytes[SCUMM_RESOURCE_TYPES][SCUMM_RESOURCE_SLOTS];
    char sha256[SCUMM_RESOURCE_TYPES][SCUMM_RESOURCE_SLOTS][65];
} ScummResourceBank;

/* Startup-only, synchronous: failure leaves both outputs unchanged. */
bool scumm_resource_bank_load(const char *manifest_path,
                             const uint8_t *code, size_t code_size,
                             ScummRuntime *runtime, ScummResourceBank **bank,
                             Error **errp);
void scumm_resource_bank_free(ScummResourceBank *bank);

#endif
