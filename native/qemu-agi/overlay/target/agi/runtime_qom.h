/* SPDX-License-Identifier: GPL-2.0-or-later
 * QEMU-only package ownership and JSON adapters for the portable AGI core.
 */
#ifndef FDISBULL_AGI_RUNTIME_QOM_H
#define FDISBULL_AGI_RUNTIME_QOM_H

#include "qapi/error.h"
#include "runtime.h"

#define AGI_RUNTIME_PACKAGE_SCHEMA "fdisbull-agi-runtime-package-1"
#define AGI_RUNTIME_STATE_SCHEMA "fdisbull-agi-runtime-state-1"
#define AGI_RUNTIME_EVENTS_SCHEMA "fdisbull-agi-runtime-events-1"
#define AGI_RUNTIME_SCENE_SCHEMA "fdisbull-agi-runtime-scene-1"
#define AGI_RUNTIME_SOUND_SCHEMA "fdisbull-agi-runtime-sound-events-1"
#define AGI_RUNTIME_SOUND_CAPACITY 262144u
#define AGI_RUNTIME_PACKAGE_MAX (64u * 1024u * 1024u)
#define AGI_RUNTIME_RESOURCE_MAX (2u * 1024u * 1024u)

/* Returned runtime owns immutable resources and event storage. Its event
 * limit is 65536 and its initial capacity is 4096; observations start off.
 * Free only runtimes created by this loader with agi_runtime_free(). */
AgiRuntime *agi_runtime_load_package(const char *filename, Error **errp);
void agi_runtime_free(AgiRuntime *runtime);

/* Each successful string result is owned by the caller (g_free).
 * All serializers are read-only. Failures return NULL and set errp. */
char *agi_runtime_state_json(const AgiRuntime *runtime, Error **errp);
char *agi_runtime_events_json(const AgiRuntime *runtime, Error **errp);
char *agi_runtime_scene_json(const AgiRuntime *runtime, Error **errp);
char *agi_runtime_snapshot_hex(const AgiRuntime *runtime, Error **errp);
/* Nondestructive bounded audio journal, independent of DISASM/SCENE.
 * Overflow is explicit in dropped, never hidden by guest/observer controls.
 * Compact rows use the returned columns; acknowledge a complete capture with
 * {action:"sound-clear",epoch:<epoch>,through:<last_seq>}. Stale clears fail. */
char *agi_runtime_sound_json(const AgiRuntime *runtime, Error **errp);

/* Strict command parsing and core preconditions; failure leaves runtime
 * state and observer bookkeeping unchanged. No implicit execution/run. */
bool agi_runtime_command_json(AgiRuntime *runtime, const char *text, Error **errp);

#endif
