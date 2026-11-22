/* SPDX-License-Identifier: GPL-2.0-or-later
 * Native presentation payloads; no host resource decoder or implicit I/O.
 * Shake order/magnitude and show.obj placement follow pinned Sarien
 * aaef5e667757385b5b3650cc1f7365908720f7e6: src/op_cmd.c:859-881,
 * src/graphics.c:137-202 and src/sprite.c:810-847. VIEW description offset
 * follows src/view.c:138-139, with explicit resource bounds added here.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qobject/qdict.h"
#include "qobject/qjson.h"
#include "qobject/qlist.h"
#include "qobject/qnum.h"
#include "runtime_devices.h"
#include "runtime_scene.h"

static void put_uint(QDict *dict, const char *key, uint64_t value)
{
    qdict_put(dict, key, qnum_from_uint(value));
}

static bool put_hex(QDict *dict, const char *key, const uint8_t *bytes,
                    size_t count, Error **errp)
{
    static const char digits[] = "0123456789abcdef";
    g_autofree char *hex = NULL;
    size_t i;
    if (count > (SIZE_MAX - 1) / 2 || !(hex = g_try_malloc(count * 2 + 1))) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for presentation bytes");
        return false;
    }
    for (i = 0; i < count; i++) {
        hex[2 * i] = digits[bytes[i] >> 4];
        hex[2 * i + 1] = digits[bytes[i] & 15];
    }
    hex[count * 2] = 0;
    qdict_put_str(dict, key, hex);
    return true;
}

static bool put_text(QDict *dict, const char *key, const char *hex_key,
                     const uint8_t *bytes, size_t count, Error **errp)
{
    g_autofree char *display = NULL;
    GError *conversion_error = NULL;
    display = g_convert((const char *)bytes, count, "UTF-8", "CP437",
                        NULL, NULL, &conversion_error);
    if (!display) {
        error_setg(errp, "AGI_RUNTIME: CP437 presentation conversion failed: %s",
                   conversion_error ? conversion_error->message : "unknown error");
        g_clear_error(&conversion_error);
        return false;
    }
    qdict_put_str(dict, key, display);
    return put_hex(dict, hex_key, bytes, count, errp);
}

static QDict *source_object(const AgiRuntime *r)
{
    QDict *source = qdict_new();
    qdict_put_str(source, "sha256", r->resources->sha256);
    qdict_put_str(source, "profile", AGI_RUNTIME_PROFILE);
    put_uint(source, "logic_id", r->state.logic);
    qdict_put_str(source, "logic_sha256",
                  r->resources->logics[r->state.logic].code.sha256);
    return source;
}

static QDict *request_object(const AgiRuntimePending *p)
{
    QDict *request = qdict_new();
    QList *args = qlist_new();
    uint32_t i;
    put_uint(request, "id", p->id);
    put_uint(request, "opcode", p->opcode);
    put_uint(request, "logic", p->logic);
    put_uint(request, "pc", p->pc);
    put_uint(request, "next_pc", p->next_pc);
    qdict_put_str(request, "reply", agi_runtime_reply_name(p->reply));
    for (i = 0; i < p->argc; i++) {
        qlist_append_int(args, p->args[i]);
    }
    qdict_put(request, "args", args);
    return request;
}

static bool scene_payload(const AgiRuntime *r, QDict *out, Error **errp)
{
    g_autofree uint8_t *planes = g_try_malloc(2 * AGI_RUNTIME_PLANE_BYTES);
    if (!planes) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for presentation planes");
        return false;
    }
    if (!agi_runtime_scene(r, planes, planes + AGI_RUNTIME_PLANE_BYTES,
                            AGI_RUNTIME_PLANE_BYTES)) {
        error_setg(errp, "AGI_RUNTIME: native presentation scene composition failed");
        return false;
    }
    put_uint(out, "width", AGI_RUNTIME_WIDTH);
    put_uint(out, "height", AGI_RUNTIME_HEIGHT);
    put_uint(out, "revision", r->state.scene_revision);
    put_uint(out, "presentation_revision", r->state.presentation_revision);
    qdict_put_bool(out, "picture_shown", !!r->state.picture_shown);
    qdict_put_str(out, "pixel_format", "ega-index8");
    return put_hex(out, "visual", planes, AGI_RUNTIME_PLANE_BYTES, errp) &&
           put_hex(out, "priority", planes + AGI_RUNTIME_PLANE_BYTES,
                    AGI_RUNTIME_PLANE_BYTES, errp);
}

static bool shake_payload(const AgiRuntime *r, QDict *out, Error **errp)
{
    const AgiRuntimeState *s = &r->state;
    QList *frames = qlist_new();
    uint32_t i, count = s->pending.args[0];
    qdict_put(out, "frames", frames);
    qdict_put_str(out, "kind", "shake-screen");
    put_uint(out, "count", count);
    put_uint(out, "frame_count", 4 * count);
    qdict_put_str(out, "coordinate_space", "display-pixels");
    put_uint(out, "display_width", 320);
    put_uint(out, "display_height", 200);
    put_uint(out, "picture_scale_x", 2);
    put_uint(out, "picture_scale_y", 1);
    put_uint(out, "picture_origin_x", 0);
    put_uint(out, "picture_origin_y", s->min_print_line * 8);
    qdict_put_bool(out, "restore_original", true);
    for (i = 0; i < 4 * count; i++) {
        QDict *frame = qdict_new();
        put_uint(frame, "index", i);
        qdict_put_int(frame, "dx", (i & 1) ? 0 : -3);
        qdict_put_int(frame, "dy", (i & 1) ? 0 : -3);
        qlist_append(frames, frame);
    }
    /* Logical text accompanies the picture, so a host can shake the complete
     * presentation without interpreting any game resource or advancing AGI. */
    put_uint(out, "text_columns", 40);
    put_uint(out, "text_rows", 25);
    qdict_put_str(out, "text_encoding", "cp437");
    return scene_payload(r, out, errp) &&
           put_hex(out, "text_hex", &s->text[0][0], sizeof(s->text), errp) &&
           put_hex(out, "text_fg_hex", &s->text_fg[0][0], sizeof(s->text_fg), errp) &&
           put_hex(out, "text_bg_hex", &s->text_bg[0][0], sizeof(s->text_bg), errp);
}

static bool inventory_payload(const AgiRuntime *r, QDict *out, Error **errp)
{
    QList *entries = qlist_new();
    uint32_t i;
    bool selectable = r->state.pending.reply == AGI_RT_REPLY_NUMBER;
    qdict_put(out, "entries", entries);
    qdict_put_str(out, "kind", "inventory");
    qdict_put_bool(out, "selectable", selectable);
    put_uint(out, "carried_room", 255);
    if (selectable) {
        put_uint(out, "selection_variable", 25);
        put_uint(out, "cancel_value", 255);
    } else {
        qdict_put_null(out, "selection_variable");
        qdict_put_null(out, "cancel_value");
    }
    for (i = 0; i < r->resources->object_count; i++) {
        const char *name = r->resources->object_names[i];
        const char *end = name ? memchr(name, 0, 256) : NULL;
        QDict *entry;
        if (!end) {
            error_setg(errp, "AGI_RUNTIME: object %u has no bounded native name", i);
            return false;
        }
        entry = qdict_new();
        qlist_append(entries, entry);
        put_uint(entry, "id", i);
        put_uint(entry, "room", r->state.inventory[i]);
        qdict_put_bool(entry, "carried", r->state.inventory[i] == 255);
        if (!put_text(entry, "name", "name_hex", (const uint8_t *)name,
                        end - name, errp)) {
            return false;
        }
    }
    return true;
}

static bool object_payload(const AgiRuntime *r, QDict *out, Error **errp)
{
    const AgiRuntimePending *p = &r->state.pending;
    uint32_t view = p->opcode == 129 ? p->args[0] : r->state.v[p->args[0]];
    const AgiRuntimeBlob *blob = &r->resources->views[view];
    g_autofree uint8_t *pixels = NULL;
    AgiRuntimeViewCel cel;
    const uint8_t *description, *end;
    uint32_t offset;
    int result;
    if (!blob->data || blob->size < 5 || blob->size > AGI_RUNTIME_RESOURCE_MAX) {
        error_setg(errp, "AGI_RUNTIME: show.obj requires a bounded VIEW %u", view);
        return false;
    }
    pixels = g_try_malloc(AGI_RUNTIME_PLANE_BYTES);
    if (!pixels) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for native VIEW pixels");
        return false;
    }
    result = agi_runtime_view_cel(blob->data, blob->size, 0, 0, pixels,
                                  AGI_RUNTIME_PLANE_BYTES, &cel);
    if (result != AGI_RS_SUCCESS) {
        error_setg(errp, "AGI_RUNTIME: show.obj VIEW %u loop0/cel0: %s", view,
                    agi_runtime_scene_error(result));
        return false;
    }
    offset = blob->data[3] | ((uint32_t)blob->data[4] << 8);
    if (offset >= blob->size) {
        error_setg(errp, "AGI_RUNTIME: show.obj VIEW %u description offset is outside its resource", view);
        return false;
    }
    description = offset ? blob->data + offset : (const uint8_t *)"";
    end = offset ? memchr(description, 0, blob->size - offset) : description;
    if (!end) {
        error_setg(errp, "AGI_RUNTIME: show.obj VIEW %u description is not terminated", view);
        return false;
    }
    qdict_put_str(out, "kind", "show-object");
    put_uint(out, "view", view);
    put_uint(out, "loop", 0);
    put_uint(out, "cel", 0);
    qdict_put_str(out, "view_sha256", blob->sha256);
    put_uint(out, "width", cel.geometry.width);
    put_uint(out, "height", cel.geometry.height);
    put_uint(out, "transparent", cel.transparent);
    qdict_put_bool(out, "mirrored", !!cel.mirrored);
    qdict_put_str(out, "pixel_format", "ega-index8");
    qdict_put_str(out, "coordinate_space", "picture-pixels");
    put_uint(out, "x", (AGI_RUNTIME_WIDTH - cel.geometry.width) / 2);
    put_uint(out, "y", 112);
    put_uint(out, "clip_width", AGI_RUNTIME_WIDTH);
    put_uint(out, "clip_height", AGI_RUNTIME_HEIGHT);
    qdict_put_bool(out, "restore_original", true);
    put_uint(out, "description_offset", offset);
    return put_hex(out, "pixels", pixels,
                    (size_t)cel.geometry.width * cel.geometry.height, errp) &&
           put_text(out, "description", "description_hex", description,
                     end - description, errp);
}

static void actor_payload(const AgiRuntime *r, QDict *out)
{
    uint32_t id = r->state.v[r->state.pending.args[0]];
    const AgiRuntimeActor *a = &r->state.world.actors[id];
    QDict *actor = qdict_new();
    qdict_put_str(out, "kind", "actor-status");
    put_uint(out, "variable", r->state.pending.args[0]);
    qdict_put(out, "actor", actor);
    put_uint(actor, "id", id);
#define ACTOR_I(name) qdict_put_int(actor, #name, a->name)
#define ACTOR_U(name) put_uint(actor, #name, a->name)
    ACTOR_I(x); ACTOR_I(y); ACTOR_I(prev_x); ACTOR_I(prev_y);
    ACTOR_I(target_x); ACTOR_I(target_y);
    ACTOR_U(width); ACTOR_U(height); ACTOR_U(prev_width); ACTOR_U(prev_height);
    ACTOR_U(view); ACTOR_U(loop); ACTOR_U(cel); ACTOR_U(loop_count); ACTOR_U(cel_count);
    ACTOR_U(priority); ACTOR_U(flags); ACTOR_U(motion); ACTOR_U(cycle); ACTOR_U(direction);
    ACTOR_U(step_size); ACTOR_U(step_time); ACTOR_U(step_time_count);
    ACTOR_U(cycle_time); ACTOR_U(cycle_time_count);
    ACTOR_U(motion_flag); ACTOR_U(cycle_flag); ACTOR_U(saved_step);
    ACTOR_U(follow_step); ACTOR_U(follow_count);
#undef ACTOR_I
#undef ACTOR_U
    qdict_put_bool(actor, "animated", !!(a->flags & AGI_RA_ANIMATED));
    qdict_put_bool(actor, "drawn", !!(a->flags & AGI_RA_DRAWN));
    qdict_put_bool(actor, "updating", !!(a->flags & AGI_RA_UPDATE));
    qdict_put_bool(actor, "cycling", !!(a->flags & AGI_RA_CYCLING));
    qdict_put_bool(actor, "view_bound", !!(a->flags & AGI_RA_VIEW_BOUND));
}

char *agi_runtime_presentation_json(const AgiRuntime *r, Error **errp)
{
    const AgiRuntimePending *p;
    QDict *root, *out;
    GString *json;
    uint32_t argc;
    bool ok = true;
    if (!r || !r->resources || r->state.logic > 255 ||
        r->resources->object_count > 256) {
        error_setg(errp, "AGI_RUNTIME: unavailable native presentation state");
        return NULL;
    }
    p = &r->state.pending;
    if (r->state.status == AGI_RT_PENDING &&
        (!p->id || p->logic != r->state.logic || p->pc != r->state.pc ||
         p->argc > 7 || p->opcode > 173 || p->reply > AGI_RT_REPLY_RESTORE ||
         p->next_pc <= p->pc ||
         p->next_pc > r->resources->logics[p->logic].code.size)) {
        error_setg(errp, "AGI_RUNTIME: invalid native presentation request");
        return NULL;
    }
    root = qdict_new();
    qdict_put_str(root, "schema", AGI_RUNTIME_PRESENTATION_SCHEMA);
    qdict_put(root, "source", source_object(r));
    qdict_put_null(root, "presentation");
    if (r->state.status != AGI_RT_PENDING) {
        qdict_put_null(root, "request");
        goto done;
    }
    qdict_put(root, "request", request_object(p));
    switch (p->opcode) {
    case 29: case 124: case 139: argc = 0; break;
    case 110: case 129: case 133: case 162: argc = 1; break;
    default: goto done;
    }
    if (p->argc != argc) {
        error_setg(errp, "AGI_RUNTIME: native presentation argument count mismatch");
        qobject_unref(root);
        return NULL;
    }
    out = qdict_new();
    qdict_put(root, "presentation", out);
    switch (p->opcode) {
    case 29:
        qdict_put_str(out, "kind", "priority-plane");
        qdict_put_str(out, "presented_plane", "priority");
        ok = scene_payload(r, out, errp);
        break;
    case 110: ok = shake_payload(r, out, errp); break;
    case 124: ok = inventory_payload(r, out, errp); break;
    case 129: case 162: ok = object_payload(r, out, errp); break;
    case 133: actor_payload(r, out); break;
    case 139:
        qdict_put_str(out, "kind", "joystick-calibration");
        qdict_put_str(out, "device", "joystick");
        qdict_put_str(out, "completion", "ack");
        qdict_put_bool(out, "requires_host_result", true);
        qdict_put_bool(out, "guest_calibration_storage", false);
        break;
    }
    if (!ok) {
        qobject_unref(root);
        return NULL;
    }
done:
    json = qobject_to_json(QOBJECT(root));
    qobject_unref(root);
    return g_string_free(json, false);
}
