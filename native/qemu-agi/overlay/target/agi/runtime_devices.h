/* SPDX-License-Identifier: GPL-2.0-or-later
 * Read-only native presentation requests for an explicitly attached host.
 */
#ifndef FDISBULL_AGI_RUNTIME_DEVICES_H
#define FDISBULL_AGI_RUNTIME_DEVICES_H

#include "qapi/error.h"
#include "runtime.h"

#define AGI_RUNTIME_PRESENTATION_SCHEMA "fdisbull-agi-runtime-presentation-1"

/* Return a caller-owned (g_free) JSON string. A query neither acknowledges
 * a pending operation nor advances guest execution, clocks or observations.
 * source identifies immutable package/current LOGIC bytes; request binds the
 * payload to the pending id/opcode/LOGIC/PC. request and presentation are null
 * without a pending request; presentation is null for other effect classes.
 *
 * Supported presentation kinds are priority-plane, shake-screen, inventory,
 * show-object, actor-status and joystick-calibration. Image pixels come from
 * the native scene/VIEW decoder. Native strings are CP437, exposed as Unicode
 * plus exact lowercase hex. No host resource decoder is needed.
 *
 * shake-screen supplies 4*count ordered offsets in 320x200 display pixels,
 * alternating (-3,-3) and (0,0), with explicit restoration to the original.
 * Host presentation timing is external and never changes the guest clock.
 * joystick-calibration describes an external request only: the host must
 * obtain a device result before completing it, and no successful hardware
 * calibration is inferred from querying or acknowledging a request. */
char *agi_runtime_presentation_json(const AgiRuntime *runtime, Error **errp);

#endif
