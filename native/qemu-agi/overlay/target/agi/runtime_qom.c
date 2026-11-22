/* SPDX-License-Identifier: GPL-2.0-or-later
 * QEMU package/transport boundary. The portable core owns AGI semantics.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qobject/qbool.h"
#include "qobject/qdict.h"
#include "qobject/qjson.h"
#include "qobject/qlist.h"
#include "qobject/qnum.h"
#include "qobject/qstring.h"
#include "runtime_qom.h"

typedef struct AgiOwnedRuntime {
    AgiRuntime runtime; /* returned address; remains the first member */
    AgiRuntimeResources resources;
    AgiRuntimeEvent *event_storage;
} AgiOwnedRuntime;

static bool keys_match(const QDict *dict, const char *const *names,
                       size_t count, size_t required, const char *label,
                       Error **errp)
{
    const QDictEntry *entry;
    size_t i;
    if (!dict) {
        error_setg(errp, "AGI_RUNTIME: %s must be an object", label);
        return false;
    }
    for (i = 0; i < required; i++) {
        if (!qdict_haskey(dict, names[i])) {
            error_setg(errp, "AGI_RUNTIME: %s requires %s", label, names[i]);
            return false;
        }
    }
    for (entry = qdict_first(dict); entry; entry = qdict_next(dict, entry)) {
        for (i = 0; i < count; i++) {
            if (!strcmp(qdict_entry_key(entry), names[i])) {
                break;
            }
        }
        if (i == count) {
            error_setg(errp, "AGI_RUNTIME: unknown %s field %s", label,
                       qdict_entry_key(entry));
            return false;
        }
    }
    return true;
}

static bool uint_value(QObject *obj, uint64_t maximum, uint64_t *out,
                       const char *label, Error **errp)
{
    QNum *num = qobject_to(QNum, obj);
    if (!num || !qnum_get_try_uint(num, out) || *out > maximum) {
        error_setg(errp, "AGI_RUNTIME: %s requires an integer in 0..%" PRIu64,
                   label, maximum);
        return false;
    }
    return true;
}

static const char *text_value(QObject *obj, size_t maximum, const char *label,
                              Error **errp)
{
    QString *str = qobject_to(QString, obj);
    const char *value = str ? qstring_get_str(str) : NULL;
    /* QEMU represents escaped NUL as modified UTF-8 C0 80. Ordinary UTF-8
     * validation rejects that representation, as well as malformed Unicode. */
    if (!value || strlen(value) > maximum || !g_utf8_validate(value, -1, NULL)) {
        error_setg(errp, "AGI_RUNTIME: %s requires non-NUL UTF-8 text of at most %zu bytes",
                   label, maximum);
        return NULL;
    }
    return value;
}

static const QList *array_value(QObject *obj, size_t maximum,
                                const char *label, Error **errp)
{
    const QList *list = qobject_to(QList, obj);
    if (!list || qlist_size(list) > maximum) {
        error_setg(errp, "AGI_RUNTIME: %s requires an array of at most %zu entries",
                   label, maximum);
        return NULL;
    }
    return list;
}

static char *try_copy(const char *text, Error **errp)
{
    size_t bytes = strlen(text) + 1;
    char *out = g_try_malloc(bytes);
    if (!out) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for resource text");
        return NULL;
    }
    memcpy(out, text, bytes);
    return out;
}

static char *utf8_to_agi(const char *text, size_t maximum, Error **errp)
{
    GError *error = NULL;
    gsize bytes;
    char *out = g_convert(text, -1, "CP437", "UTF-8", NULL, &bytes, &error);
    if (!out) {
        error_setg(errp, "AGI_RUNTIME: text is not representable as CP437: %s",
                   error ? error->message : "conversion failed");
        g_clear_error(&error);
        return NULL;
    }
    if (bytes > maximum) {
        g_free(out);
        error_setg(errp, "AGI_RUNTIME: text exceeds %zu native CP437 bytes", maximum);
        return NULL;
    }
    return out;
}

static char *agi_to_utf8(const char *text, size_t maximum, Error **errp)
{
    GError *error = NULL;
    char *out = g_convert(text, strnlen(text, maximum), "UTF-8", "CP437", NULL, NULL, &error);
    if (!out) {
        error_setg(errp, "AGI_RUNTIME: CP437 display conversion failed: %s",
                   error ? error->message : "conversion failed");
        g_clear_error(&error);
    }
    return out;
}

static int lower_hex_value(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

static uint8_t *decode_hex(const char *hex, size_t minimum, size_t maximum,
                           size_t *size, const char *label, Error **errp)
{
    uint8_t *data;
    size_t n = hex ? strlen(hex) : 0, i;
    if (!hex || (n & 1) || n / 2 < minimum || n / 2 > maximum) {
        error_setg(errp, "AGI_RUNTIME: %s requires %zu..%zu bytes of lowercase hex",
                   label, minimum, maximum);
        return NULL;
    }
    for (i = 0; i < n; i++) {
        if (lower_hex_value(hex[i]) < 0) {
            error_setg(errp, "AGI_RUNTIME: %s contains non-lowercase-hex data", label);
            return NULL;
        }
    }
    data = g_try_malloc(n / 2 ? n / 2 : 1);
    if (!data) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for %s", label);
        return NULL;
    }
    for (i = 0; i < n / 2; i++) {
        data[i] = (lower_hex_value(hex[i * 2]) << 4) |
                   lower_hex_value(hex[i * 2 + 1]);
    }
    *size = n / 2;
    return data;
}

static bool blob_value(QDict *record, const char *field, size_t maximum,
                       AgiRuntimeBlob *out, Error **errp)
{
    const char *hex = text_value(qdict_get(record, field), maximum * 2, field, errp);
    const char *digest;
    g_autofree char *actual = NULL;
    uint8_t *data;
    size_t size, i;
    if (!hex) {
        return false;
    }
    digest = text_value(qdict_get(record, "sha256"), 64, "sha256", errp);
    if (!digest) {
        return false;
    }
    if (strlen(digest) != 64) {
        error_setg(errp, "AGI_RUNTIME: sha256 must have 64 lowercase hex digits");
        return false;
    }
    for (i = 0; i < 64; i++) {
        if (lower_hex_value(digest[i]) < 0) {
            error_setg(errp, "AGI_RUNTIME: sha256 must have 64 lowercase hex digits");
            return false;
        }
    }
    data = decode_hex(hex, 1, maximum, &size, field, errp);
    if (!data) {
        return false;
    }
    actual = g_compute_checksum_for_data(G_CHECKSUM_SHA256, data, size);
    if (strcmp(actual, digest)) {
        g_free(data);
        error_setg(errp, "AGI_RUNTIME: sha256 differs from exact %s bytes", field);
        return false;
    }
    out->data = data;
    out->size = size;
    memcpy(out->sha256, actual, sizeof(out->sha256));
    return true;
}

static bool load_logics(QDict *package, AgiRuntimeResources *resources,
                        Error **errp)
{
    static const char *const fields[] = {"id", "code", "sha256", "messages"};
    const QList *rows = array_value(qdict_get(package, "logics"), 256, "logics", errp);
    const QListEntry *entry;
    if (!rows) {
        return false;
    }
    for (entry = qlist_first(rows); entry; entry = qlist_next(entry)) {
        QDict *record = qobject_to(QDict, qlist_entry_obj(entry));
        const QList *messages;
        const QListEntry *message;
        AgiRuntimeLogic *logic;
        uint64_t id;
        unsigned slot = 1;
        if (!keys_match(record, fields, G_N_ELEMENTS(fields), G_N_ELEMENTS(fields),
                         "logic", errp) ||
            !uint_value(qdict_get(record, "id"), 255, &id, "logic.id", errp)) {
            return false;
        }
        logic = &resources->logics[id];
        if (logic->code.data) {
            error_setg(errp, "AGI_RUNTIME: duplicate logic id %" PRIu64, id);
            return false;
        }
        if (!blob_value(record, "code", AGI_CODE_MAX, &logic->code, errp)) {
            return false;
        }
        messages = array_value(qdict_get(record, "messages"), 255, "logic.messages", errp);
        if (!messages) {
            return false;
        }
        logic->message_count = qlist_size(messages);
        for (message = qlist_first(messages); message; message = qlist_next(message), slot++) {
            QObject *value = qlist_entry_obj(message);
            const char *text;
            if (qobject_type(value) == QTYPE_QNULL) {
                continue;
            }
            text = text_value(value, (AGI_RT_TEXT_BYTES - 1) * 3, "logic message", errp);
            if (!text) {
                return false;
            }
            logic->messages[slot] = utf8_to_agi(text, AGI_RT_TEXT_BYTES - 1, errp);
            if (!logic->messages[slot]) {
                return false;
            }
        }
    }
    return true;
}

static bool load_blobs(QDict *package, const char *kind, AgiRuntimeBlob blobs[256],
                       Error **errp)
{
    static const char *const fields[] = {"id", "data", "sha256"};
    const QList *rows = array_value(qdict_get(package, kind), 256, kind, errp);
    const QListEntry *entry;
    if (!rows) {
        return false;
    }
    for (entry = qlist_first(rows); entry; entry = qlist_next(entry)) {
        QDict *record = qobject_to(QDict, qlist_entry_obj(entry));
        uint64_t id;
        if (!keys_match(record, fields, G_N_ELEMENTS(fields), G_N_ELEMENTS(fields), kind, errp) ||
            !uint_value(qdict_get(record, "id"), 255, &id, "resource.id", errp)) {
            return false;
        }
        if (blobs[id].data) {
            error_setg(errp, "AGI_RUNTIME: duplicate %s id %" PRIu64, kind, id);
            return false;
        }
        if (!blob_value(record, "data", AGI_RUNTIME_RESOURCE_MAX, &blobs[id], errp)) {
            return false;
        }
    }
    return true;
}

static bool load_words(QDict *package, AgiRuntimeResources *resources, Error **errp)
{
    static const char *const fields[] = {"text", "id"};
    const QList *rows = array_value(qdict_get(package, "words"), 10000, "words", errp);
    const QListEntry *entry;
    g_autoptr(GHashTable) seen = g_hash_table_new(g_str_hash, g_str_equal);
    AgiRuntimeWord *words;
    unsigned index = 0;
    if (!rows) {
        return false;
    }
    words = g_try_new0(AgiRuntimeWord, qlist_size(rows) + 1);
    if (!words) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for words");
        return false;
    }
    resources->words = words;
    resources->word_count = qlist_size(rows);
    for (entry = qlist_first(rows); entry; entry = qlist_next(entry), index++) {
        QDict *record = qobject_to(QDict, qlist_entry_obj(entry));
        const char *text;
        size_t i;
        uint64_t id;
        if (!keys_match(record, fields, G_N_ELEMENTS(fields), G_N_ELEMENTS(fields), "word", errp) ||
            !uint_value(qdict_get(record, "id"), 65535, &id, "word.id", errp)) {
            return false;
        }
        text = text_value(qdict_get(record, "text"), 63, "word.text", errp);
        if (!text) {
            return false;
        }
        if (!text[0]) {
            error_setg(errp, "AGI_RUNTIME: word.text must be nonempty");
            return false;
        }
        for (i = 0; text[i]; i++) {
            if ((unsigned char)text[i] < 32 || (unsigned char)text[i] > 126 ||
                (text[i] >= 'A' && text[i] <= 'Z')) {
                error_setg(errp, "AGI_RUNTIME: word.text must be lowercase printable ASCII");
                return false;
            }
        }
        if (g_hash_table_contains(seen, text)) {
            error_setg(errp, "AGI_RUNTIME: duplicate word text");
            return false;
        }
        words[index].text = try_copy(text, errp);
        if (!words[index].text) {
            return false;
        }
        words[index].id = id;
        g_hash_table_add(seen, (void *)words[index].text);
    }
    return true;
}

static bool load_objects(QDict *package, AgiRuntimeResources *resources, Error **errp)
{
    static const char *const fields[] = {"name", "room"};
    const QList *rows = array_value(qdict_get(package, "objects"), 256, "objects", errp);
    const QListEntry *entry;
    unsigned index = 0;
    if (!rows) {
        return false;
    }
    resources->object_count = qlist_size(rows);
    for (entry = qlist_first(rows); entry; entry = qlist_next(entry), index++) {
        QDict *record = qobject_to(QDict, qlist_entry_obj(entry));
        const char *name;
        uint64_t room;
        if (!keys_match(record, fields, G_N_ELEMENTS(fields), G_N_ELEMENTS(fields), "object", errp) ||
            !uint_value(qdict_get(record, "room"), 255, &room, "object.room", errp)) {
            return false;
        }
        name = text_value(qdict_get(record, "name"), 255 * 3, "object.name", errp);
        if (!name) {
            return false;
        }
        resources->object_names[index] = utf8_to_agi(name, 255, errp);
        if (!resources->object_names[index]) {
            return false;
        }
        resources->object_rooms[index] = room;
    }
    return true;
}

/* QEMU accepts a few JSON extensions. The package/command contract uses
 * ordinary JSON: do not accept single-quoted strings or the \\' escape. */
static bool standard_json(const char *text, size_t size, Error **errp)
{
    size_t i;
    bool quoted = false, escape = false;
    if (memchr(text, 0, size) || !g_utf8_validate(text, size, NULL)) {
        error_setg(errp, "AGI_RUNTIME: JSON must be non-NUL UTF-8");
        return false;
    }
    for (i = 0; i < size; i++) {
        if (escape) {
            if (text[i] == '\'') {
                error_setg(errp, "AGI_RUNTIME: nonstandard JSON escape");
                return false;
            }
            escape = false;
        } else if (quoted && text[i] == '\\') {
            escape = true;
        } else if (text[i] == '"') {
            quoted = !quoted;
        } else if (!quoted && text[i] == '\'') {
            error_setg(errp, "AGI_RUNTIME: JSON strings require double quotes");
            return false;
        }
    }
    return true;
}

static char *read_package(const char *filename, size_t *size, Error **errp)
{
    struct stat st;
    FILE *file;
    char *data;
    size_t got;
    int fd, saved_errno;
    if (!filename || !filename[0]) {
        error_setg(errp, "AGI_RUNTIME: package filename is required");
        return NULL;
    }
    fd = open(filename, O_RDONLY | O_NONBLOCK);
    if (fd < 0) {
        error_setg_errno(errp, errno, "AGI_RUNTIME: cannot open package");
        return NULL;
    }
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size < 1 ||
        st.st_size > AGI_RUNTIME_PACKAGE_MAX) {
        close(fd);
        error_setg(errp, "AGI_RUNTIME: package must be a 1..64MiB regular file");
        return NULL;
    }
    data = g_try_malloc((size_t)st.st_size + 1);
    if (!data) {
        close(fd);
        error_setg(errp, "AGI_RUNTIME: insufficient memory for package");
        return NULL;
    }
    file = fdopen(fd, "rb");
    if (!file) {
        saved_errno = errno;
        close(fd);
        g_free(data);
        error_setg_errno(errp, saved_errno, "AGI_RUNTIME: cannot read package");
        return NULL;
    }
    got = fread(data, 1, (size_t)st.st_size + 1, file);
    if (ferror(file) || got != (size_t)st.st_size) {
        fclose(file);
        g_free(data);
        error_setg(errp, "AGI_RUNTIME: package read failed or file extent changed");
        return NULL;
    }
    fclose(file);
    data[got] = 0;
    *size = got;
    return data;
}

void agi_runtime_free(AgiRuntime *runtime)
{
    AgiOwnedRuntime *owned = (AgiOwnedRuntime *)runtime;
    unsigned i, j;
    if (!owned) {
        return;
    }
    for (i = 0; i < 256; i++) {
        g_free((void *)owned->resources.logics[i].code.data);
        g_free((void *)owned->resources.views[i].data);
        g_free((void *)owned->resources.pictures[i].data);
        g_free((void *)owned->resources.sounds[i].data);
        g_free((void *)owned->resources.object_names[i]);
        for (j = 0; j < 256; j++) {
            g_free((void *)owned->resources.logics[i].messages[j]);
        }
    }
    for (i = 0; i < owned->resources.word_count; i++) {
        g_free((void *)owned->resources.words[i].text);
    }
    g_free((void *)owned->resources.words);
    g_free(owned->event_storage);
    g_free(owned);
}

AgiRuntime *agi_runtime_load_package(const char *filename, Error **errp)
{
    static const char *const fields[] = {
        "schema", "profile", "entry_logic", "logics", "views", "pictures",
        "sounds", "words", "objects"
    };
    g_autofree char *data = NULL;
    g_autofree char *digest = NULL;
    QObject *root = NULL;
    QDict *package;
    AgiOwnedRuntime *owned = NULL;
    const char *schema, *profile;
    uint64_t entry;
    size_t size;
    data = read_package(filename, &size, errp);
    if (!data || !standard_json(data, size, errp)) {
        return NULL;
    }
    root = qobject_from_json(data, errp);
    if (!root) {
        return NULL;
    }
    package = qobject_to(QDict, root);
    if (!keys_match(package, fields, G_N_ELEMENTS(fields), G_N_ELEMENTS(fields), "package", errp)) {
        goto fail;
    }
    schema = text_value(qdict_get(package, "schema"), 64, "schema", errp);
    if (!schema) {
        goto fail;
    }
    profile = text_value(qdict_get(package, "profile"), 64, "profile", errp);
    if (!profile) {
        goto fail;
    }
    if (strcmp(schema, AGI_RUNTIME_PACKAGE_SCHEMA) || strcmp(profile, AGI_RUNTIME_PROFILE)) {
        error_setg(errp, "AGI_RUNTIME: unsupported explicit package schema/profile");
        goto fail;
    }
    if (!uint_value(qdict_get(package, "entry_logic"), 255, &entry, "entry_logic", errp)) {
        goto fail;
    }
    owned = g_try_new0(AgiOwnedRuntime, 1);
    if (!owned) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for runtime");
        goto fail;
    }
    owned->resources.entry_logic = entry;
    if (!load_logics(package, &owned->resources, errp) ||
        !load_blobs(package, "views", owned->resources.views, errp) ||
        !load_blobs(package, "pictures", owned->resources.pictures, errp) ||
        !load_blobs(package, "sounds", owned->resources.sounds, errp) ||
        !load_words(package, &owned->resources, errp) ||
        !load_objects(package, &owned->resources, errp)) {
        goto fail;
    }
    if (!owned->resources.logics[entry].code.data) {
        error_setg(errp, "AGI_RUNTIME: entry_logic is absent from logics");
        goto fail;
    }
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, (const uint8_t *)data, size);
    memcpy(owned->resources.sha256, digest, sizeof(owned->resources.sha256));
    owned->event_storage = g_try_new0(AgiRuntimeEvent, AGI_RT_EVENTS_MAX);
    if (!owned->event_storage) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for bounded event storage");
        goto fail;
    }
    if (!agi_runtime_init(&owned->runtime, &owned->resources,
                           owned->event_storage, AGI_RT_EVENTS_MAX)) {
        error_setg(errp, "AGI_RUNTIME: core rejected package initialization");
        goto fail;
    }
    owned->runtime.obs_capacity = 4096;
    qobject_unref(root);
    return &owned->runtime;
fail:
    qobject_unref(root);
    agi_runtime_free(owned ? &owned->runtime : NULL);
    return NULL;
}

static bool runtime_valid(const AgiRuntime *r, Error **errp)
{
    if (!r || !r->resources || r->state.logic > 255 ||
        r->obs_limit > AGI_RT_EVENTS_MAX || r->obs_capacity > r->obs_limit ||
        r->obs_count > r->obs_capacity || (r->obs_count && !r->events) ||
        r->state.pending.argc > 7 || r->state.stack_depth > AGI_RT_STACK ||
        r->state.parsed_count > AGI_RT_WORDS || r->state.key_count > 256 ||
        r->state.menu_count > AGI_RT_MENUS ||
        r->state.menu_item_count > AGI_RT_MENU_ITEMS ||
        r->state.script_count > AGI_RT_SCRIPT) {
        error_setg(errp, "AGI_RUNTIME: unavailable or invalid native runtime state");
        return false;
    }
    return true;
}

static void put_uint(QDict *dict, const char *key, uint64_t value)
{
    qdict_put(dict, key, qnum_from_uint(value));
}

static QList *byte_array(const uint8_t *data, size_t count)
{
    QList *out = qlist_new();
    size_t i;
    for (i = 0; i < count; i++) {
        qlist_append_int(out, data[i]);
    }
    return out;
}

static QList *word_array(const uint16_t *data, size_t count)
{
    QList *out = qlist_new();
    size_t i;
    for (i = 0; i < count; i++) {
        qlist_append_int(out, data[i]);
    }
    return out;
}

static QList *uint_array(const uint32_t *data, size_t count)
{
    QList *out = qlist_new();
    size_t i;
    for (i = 0; i < count; i++) {
        qlist_append(out, qnum_from_uint(data[i]));
    }
    return out;
}

static char *encode_hex(const void *data, size_t count, Error **errp)
{
    static const char digits[] = "0123456789abcdef";
    const uint8_t *bytes = data;
    char *out;
    size_t i;
    if (count > (SIZE_MAX - 1) / 2) {
        error_setg(errp, "AGI_RUNTIME: hex output exceeds addressable storage");
        return NULL;
    }
    out = g_try_malloc(count * 2 + 1);
    if (!out) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for hex output");
        return NULL;
    }
    for (i = 0; i < count; i++) {
        out[2 * i] = digits[bytes[i] >> 4];
        out[2 * i + 1] = digits[bytes[i] & 15];
    }
    out[count * 2] = 0;
    return out;
}

static bool put_hex(QDict *dict, const char *key, const void *data, size_t count,
                    Error **errp)
{
    g_autofree char *hex = encode_hex(data, count, errp);
    if (!hex) {
        return false;
    }
    qdict_put_str(dict, key, hex);
    return true;
}

static bool put_fixed_text(QDict *dict, const char *key, const char *text, size_t size,
                           Error **errp)
{
    /* The core stores original AGI CP437 bytes. Decode at the transport
     * boundary; never turn a 40-byte native string into a UTF-8 byte slot. */
    g_autofree char *display = agi_to_utf8(text, size, errp);
    if (!display) {
        return false;
    }
    qdict_put_str(dict, key, display);
    return true;
}

static char *json_string(QDict *dict)
{
    GString *out = qobject_to_json(QOBJECT(dict));
    qobject_unref(dict);
    return g_string_free(out, false);
}

static QDict *source_object(const AgiRuntime *r)
{
    QDict *source = qdict_new();
    qdict_put_str(source, "sha256", r->resources->sha256);
    qdict_put_str(source, "profile", AGI_RUNTIME_PROFILE);
    put_uint(source, "logic_id", r->state.logic);
    qdict_put_str(source, "logic_sha256", r->resources->logics[r->state.logic].code.sha256);
    return source;
}

static QDict *actor_object(const AgiRuntimeActor *a, unsigned id)
{
    QDict *out = qdict_new();
    put_uint(out, "id", id);
#define ACTOR_I(name) qdict_put_int(out, #name, a->name)
#define ACTOR_U(name) put_uint(out, #name, a->name)
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
    qdict_put_bool(out, "animated", !!(a->flags & AGI_RA_ANIMATED));
    qdict_put_bool(out, "drawn", !!(a->flags & AGI_RA_DRAWN));
    qdict_put_bool(out, "updating", !!(a->flags & AGI_RA_UPDATE));
    qdict_put_bool(out, "cycling", !!(a->flags & AGI_RA_CYCLING));
    qdict_put_bool(out, "view_bound", !!(a->flags & AGI_RA_VIEW_BOUND));
    return out;
}

static QDict *pending_object(const AgiRuntimePending *p, Error **errp)
{
    QDict *out = qdict_new();
    put_uint(out, "id", p->id);
    put_uint(out, "opcode", p->opcode);
    put_uint(out, "logic", p->logic);
    put_uint(out, "pc", p->pc);
    put_uint(out, "next_pc", p->next_pc);
    qdict_put_str(out, "reply", agi_runtime_reply_name(p->reply));
    qdict_put(out, "args", byte_array(p->args, p->argc));
    if (!put_fixed_text(out, "text", p->text, sizeof(p->text), errp)) {
        qobject_unref(out);
        return NULL;
    }
    return out;
}

static QDict *observation_object(const AgiRuntime *r)
{
    QDict *out = qdict_new(), *channels = qdict_new();
    uint32_t stored[2] = {0, 0}, i;
    for (i = 0; i < r->obs_count; i++) {
        if (r->events[i].channel < 2) {
            stored[r->events[i].channel]++;
        }
    }
    put_uint(out, "mask", r->obs_mask);
    put_uint(out, "capacity", r->obs_capacity);
    put_uint(out, "limit", r->obs_limit);
    put_uint(out, "count", r->obs_count);
    put_uint(out, "eligible", r->obs_eligible[0] + r->obs_eligible[1]);
    put_uint(out, "dropped", r->obs_dropped[0] + r->obs_dropped[1]);
    put_uint(out, "helper_calls", r->obs_calls);
    put_uint(out, "epoch", r->epoch);
    for (i = 0; i < 2; i++) {
        QDict *channel = qdict_new();
        put_uint(channel, "eligible", r->obs_eligible[i]);
        put_uint(channel, "stored", stored[i]);
        put_uint(channel, "dropped", r->obs_dropped[i]);
        qdict_put(channels, i ? "scene" : "disasm", channel);
    }
    qdict_put(out, "per_channel", channels);
    return out;
}

char *agi_runtime_state_json(const AgiRuntime *r, Error **errp)
{
    const AgiRuntimeState *s;
    QDict *root, *guest, *run, *block;
    QList *actors, *stack, *strings, *parsed, *menus, *items, *script;
    g_autofree char *state_digest = NULL;
    unsigned i;
    if (!runtime_valid(r, errp)) {
        return NULL;
    }
    s = &r->state;
    root = qdict_new();
    guest = qdict_new();
    run = qdict_new();
    qdict_put_str(root, "schema", AGI_RUNTIME_STATE_SCHEMA);
    qdict_put(root, "source", source_object(r));
    qdict_put(root, "guest", guest);
    qdict_put(root, "observation", observation_object(r));
    put_uint(run, "retired", r->run_retired);
    qdict_put(root, "run", run);
    qdict_put(guest, "variables", byte_array(s->v, 256));
    qdict_put(guest, "flags", byte_array(s->f, 256));
    qdict_put(guest, "inventory", byte_array(s->inventory, 256));
    qdict_put(guest, "loaded_logics", byte_array(s->loaded_logics, 256));
    qdict_put(guest, "loaded_pictures", byte_array(s->loaded_pictures, 256));
    qdict_put(guest, "loaded_sounds", byte_array(s->loaded_sounds, 256));
    qdict_put(guest, "loaded_views", byte_array(s->world.loaded_views, 256));
    qdict_put(guest, "priority_bands", byte_array(s->world.priority_bands, AGI_RUNTIME_HEIGHT));
    put_uint(guest, "horizon", s->world.horizon);
    put_uint(guest, "player_control", s->world.player_control);
    put_uint(guest, "priority_base", s->world.priority_base);
    put_uint(guest, "rng_state", s->world.rng_state);
    put_uint(guest, "ticks", s->world.ticks);
    block = qdict_new();
    put_uint(block, "active", s->world.block_active);
    qdict_put_int(block, "x1", s->world.block_x1);
    qdict_put_int(block, "y1", s->world.block_y1);
    qdict_put_int(block, "x2", s->world.block_x2);
    qdict_put_int(block, "y2", s->world.block_y2);
    qdict_put(guest, "block", block);
    actors = qlist_new();
    qdict_put(guest, "actors", actors);
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        qlist_append(actors, actor_object(&s->world.actors[i], i));
    }
#define STATE_U(name) put_uint(guest, #name, s->name)
    STATE_U(logic); STATE_U(pc); STATE_U(retired); STATE_U(next_effect_id);
    STATE_U(scene_revision); STATE_U(presentation_revision);
    STATE_U(cycle_count); STATE_U(clock_ticks); STATE_U(cycle_active);
    STATE_U(stack_depth); STATE_U(parsed_count); STATE_U(key_count);
    STATE_U(keypress); STATE_U(input_enabled); STATE_U(hold_key);
    STATE_U(graphics); STATE_U(foreground); STATE_U(background); STATE_U(cursor);
    STATE_U(status_line); STATE_U(min_print_line); STATE_U(input_line);
    STATE_U(status_line_row); STATE_U(window_open); STATE_U(dialogue); STATE_U(monitor);
    STATE_U(upper_left_x); STATE_U(upper_left_y); STATE_U(picture_shown); STATE_U(picture_id);
    STATE_U(sound_active); STATE_U(sound_id); STATE_U(sound_flag); STATE_U(sound_remaining);
    STATE_U(menu_count); STATE_U(menu_item_count); STATE_U(menu_submitted);
    STATE_U(simple_save); STATE_U(script_capacity); STATE_U(script_count); STATE_U(script_saved);
    STATE_U(trace_enabled); STATE_U(trace_logic); STATE_U(trace_top); STATE_U(trace_height);
#undef STATE_U
    qdict_put_str(guest, "status", agi_runtime_status_name(s->status));
    put_uint(guest, "status_code", s->status);
    put_uint(guest, "fault_code", s->fault);
    put_uint(guest, "fault_detail", s->fault_detail);
    put_uint(guest, "fault_logic", s->fault_logic);
    put_uint(guest, "fault_pc", s->fault_pc);
    if (s->fault) {
        QDict *fault = qdict_new();
        put_uint(fault, "code", s->fault);
        qdict_put_str(fault, "name", agi_runtime_error_name(s->fault));
        put_uint(fault, "detail", s->fault_detail);
        put_uint(fault, "logic", s->fault_logic);
        put_uint(fault, "pc", s->fault_pc);
        qdict_put(guest, "fault", fault);
    } else {
        qdict_put_null(guest, "fault");
    }
    if (s->status == AGI_RT_PENDING) {
        QDict *pending = pending_object(&s->pending, errp);
        if (!pending) {
            goto fail;
        }
        qdict_put(guest, "pending_effect", pending);
    } else {
        qdict_put_null(guest, "pending_effect");
    }
    qdict_put(guest, "scan_start", uint_array(s->scan_start, 256));
    stack = qlist_new();
    qdict_put(guest, "stack", stack);
    for (i = 0; i < AGI_RT_STACK; i++) {
        QDict *frame = qdict_new();
        put_uint(frame, "logic", s->stack[i].logic);
        put_uint(frame, "pc", s->stack[i].pc);
        qlist_append(stack, frame);
    }
    strings = qlist_new();
    qdict_put(guest, "strings", strings);
    for (i = 0; i < AGI_RT_STRINGS; i++) {
        g_autofree char *display = agi_to_utf8(s->strings[i], AGI_RT_STRING_BYTES, errp);
        if (!display) {
            goto fail;
        }
        qlist_append_str(strings, display);
    }
    if (!put_fixed_text(guest, "input", s->input, sizeof(s->input), errp) ||
        !put_fixed_text(guest, "echo", s->echo, sizeof(s->echo), errp) ||
        !put_fixed_text(guest, "game_id", s->game_id, sizeof(s->game_id), errp)) {
        goto fail;
    }
    qdict_put(guest, "word_ids", word_array(s->word_ids, AGI_RT_WORDS));
    parsed = qlist_new();
    qdict_put(guest, "parsed_words", parsed);
    for (i = 0; i < AGI_RT_WORDS; i++) {
        g_autofree char *display = agi_to_utf8(s->parsed_words[i], AGI_RT_STRING_BYTES, errp);
        if (!display) {
            goto fail;
        }
        qlist_append_str(parsed, display);
    }
    qdict_put(guest, "keys", word_array(s->keys, 256));
    qdict_put(guest, "key_controllers", byte_array(s->key_controllers, 256));
    qdict_put(guest, "controllers", byte_array(s->controllers, 256));
    menus = qlist_new();
    items = qlist_new();
    qdict_put(guest, "menus", menus);
    qdict_put(guest, "menu_items", items);
    for (i = 0; i < AGI_RT_MENUS; i++) {
        QDict *menu = qdict_new();
        qlist_append(menus, menu);
        put_uint(menu, "first_item", s->menus[i].first_item);
        put_uint(menu, "item_count", s->menus[i].item_count);
        if (!put_fixed_text(menu, "text", s->menus[i].text, sizeof(s->menus[i].text), errp) ||
            !put_hex(menu, "text_hex", s->menus[i].text, sizeof(s->menus[i].text), errp)) {
            goto fail;
        }
    }
    for (i = 0; i < AGI_RT_MENU_ITEMS; i++) {
        QDict *item = qdict_new();
        qlist_append(items, item);
        put_uint(item, "controller", s->menu_items[i].controller);
        put_uint(item, "enabled", s->menu_items[i].enabled);
        if (!put_fixed_text(item, "text", s->menu_items[i].text, sizeof(s->menu_items[i].text), errp) ||
            !put_hex(item, "text_hex", s->menu_items[i].text, sizeof(s->menu_items[i].text), errp)) {
            goto fail;
        }
    }
    script = qlist_new();
    qdict_put(guest, "script", script);
    for (i = 0; i < AGI_RT_SCRIPT; i++) {
        QDict *entry = qdict_new();
        put_uint(entry, "opcode", s->script[i].opcode);
        qdict_put(entry, "args", byte_array(s->script[i].args, 7));
        qlist_append(script, entry);
    }
#define STATE_HEX(name) put_hex(guest, #name "_hex", s->name, sizeof(s->name), errp)
    if (!STATE_HEX(strings) || !STATE_HEX(input) || !STATE_HEX(echo) ||
        !STATE_HEX(game_id) || !STATE_HEX(parsed_words) || !STATE_HEX(text) ||
        !STATE_HEX(text_fg) || !STATE_HEX(text_bg) || !STATE_HEX(picture_visual) ||
        !STATE_HEX(picture_priority) ||
        !put_hex(guest, "pending_storage_hex", &s->pending, sizeof(s->pending), errp)) {
        goto fail;
    }
#undef STATE_HEX
    /* Same-ABI fingerprint covers every byte, including inactive storage and
     * padding, independently of optional DISASM/SCENE observer state. */
    state_digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, (const uint8_t *)s, sizeof(*s));
    qdict_put_str(guest, "state_bytes_sha256", state_digest);
    put_uint(guest, "state_bytes_size", sizeof(*s));
    qdict_put_str(guest, "state_encoding", "agi-runtime-native-abi-1");
    return json_string(root);
fail:
    qobject_unref(root);
    return NULL;
}

char *agi_runtime_events_json(const AgiRuntime *r, Error **errp)
{
    QDict *header;
    GString *out;
    char *prefix;
    unsigned i;
    if (!runtime_valid(r, errp)) {
        return NULL;
    }
    for (i = 0; i < r->obs_count; i++) {
        if (r->events[i].size > AGI_DECODE_BYTES_MAX || r->events[i].channel > 1) {
            error_setg(errp, "AGI_RUNTIME: invalid native event extent/channel");
            return NULL;
        }
    }
    header = qdict_new();
    qdict_put_str(header, "schema", AGI_RUNTIME_EVENTS_SCHEMA);
    qdict_put(header, "source", source_object(r));
    put_uint(header, "epoch", r->epoch);
    qdict_put(header, "observation", observation_object(r));
    prefix = json_string(header);
    /* Stream one bounded QDict at a time: an explicit 65536-event request
     * must not construct tens of thousands of simultaneous hash tables. */
    out = g_string_new_len(prefix, strlen(prefix) - 1);
    g_free(prefix);
    g_string_append(out, ",\"events\":[");
    for (i = 0; i < r->obs_count; i++) {
        const AgiRuntimeEvent *e = &r->events[i];
        QDict *event = qdict_new();
        g_autofree char *serialized = NULL;
#define EVENT_U(name) put_uint(event, #name, e->name)
        EVENT_U(seq); EVENT_U(retired); EVENT_U(scene_revision); EVENT_U(logic);
        EVENT_U(pc); EVENT_U(opcode); EVENT_U(next_logic); EVENT_U(next_pc);
        EVENT_U(size); EVENT_U(actor); EVENT_U(kind);
#undef EVENT_U
        qdict_put_str(event, "channel", e->channel ? "scene" : "disasm");
        put_uint(event, "channel_id", e->channel);
        qdict_put_str(event, "logic_sha256", e->logic < 256 ? r->resources->logics[e->logic].code.sha256 : "");
        qdict_put(event, "bytes", byte_array(e->bytes, e->size));
        qdict_put(event, "resolved", uint_array(e->resolved, 7));
        if (e->kind == 1 && e->actor < 256) {
            qdict_put(event, "before_actor", actor_object(&e->before_actor, e->actor));
            qdict_put(event, "after_actor", actor_object(&e->after_actor, e->actor));
        } else {
            qdict_put_null(event, "before_actor");
            qdict_put_null(event, "after_actor");
        }
        serialized = json_string(event);
        if (i) {
            g_string_append_c(out, ',');
        }
        g_string_append(out, serialized);
    }
    g_string_append(out, "]}");
    return g_string_free(out, false);
}

char *agi_runtime_scene_json(const AgiRuntime *r, Error **errp)
{
    g_autofree uint8_t *planes = NULL;
    QDict *root;
    if (!runtime_valid(r, errp)) {
        return NULL;
    }
    planes = g_try_malloc(AGI_RUNTIME_PLANE_BYTES * 2);
    if (!planes) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for scene planes");
        return NULL;
    }
    if (!agi_runtime_scene(r, planes, planes + AGI_RUNTIME_PLANE_BYTES, AGI_RUNTIME_PLANE_BYTES)) {
        error_setg(errp, "AGI_RUNTIME: native scene composition failed");
        return NULL;
    }
    root = qdict_new();
    qdict_put_str(root, "schema", AGI_RUNTIME_SCENE_SCHEMA);
    qdict_put(root, "source", source_object(r));
    put_uint(root, "width", AGI_RUNTIME_WIDTH);
    put_uint(root, "height", AGI_RUNTIME_HEIGHT);
    put_uint(root, "revision", r->state.scene_revision);
    put_uint(root, "presentation", r->state.presentation_revision);
    put_uint(root, "picture_shown", r->state.picture_shown);
    if (!put_hex(root, "visual", planes, AGI_RUNTIME_PLANE_BYTES, errp) ||
        !put_hex(root, "priority", planes + AGI_RUNTIME_PLANE_BYTES, AGI_RUNTIME_PLANE_BYTES, errp)) {
        qobject_unref(root);
        return NULL;
    }
    return json_string(root);
}

char *agi_runtime_snapshot_hex(const AgiRuntime *r, Error **errp)
{
    g_autofree uint8_t *bytes = NULL;
    size_t size = agi_runtime_snapshot_size();
    if (!runtime_valid(r, errp)) {
        return NULL;
    }
    bytes = g_try_malloc(size);
    if (!bytes) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for snapshot");
        return NULL;
    }
    if (!agi_runtime_snapshot(r, bytes, size)) {
        error_setg(errp, "AGI_RUNTIME: native snapshot failed");
        return NULL;
    }
    return encode_hex(bytes, size, errp);
}

static bool seed_array(QDict *values, uint8_t out[256], unsigned maximum,
                       const char *label, Error **errp)
{
    const QDictEntry *entry;
    if (!values || qdict_size(values) > 256) {
        error_setg(errp, "AGI_RUNTIME: %s must be an object of at most 256 byte indexes", label);
        return false;
    }
    for (entry = qdict_first(values); entry; entry = qdict_next(values, entry)) {
        const char *key = qdict_entry_key(entry);
        uint64_t value;
        unsigned index = 0;
        size_t i, length = strlen(key);
        if (!length || length > 3 || (length > 1 && key[0] == '0')) {
            error_setg(errp, "AGI_RUNTIME: %s indexes require canonical decimal 0..255", label);
            return false;
        }
        for (i = 0; i < length; i++) {
            if (key[i] < '0' || key[i] > '9') {
                error_setg(errp, "AGI_RUNTIME: %s indexes require canonical decimal 0..255", label);
                return false;
            }
            index = index * 10 + key[i] - '0';
        }
        if (index > 255 ||
            !uint_value(qdict_entry_value(entry), maximum, &value, label, errp)) {
            if (index > 255) {
                error_setg(errp, "AGI_RUNTIME: %s index exceeds 255", label);
            }
            return false;
        }
        out[index] = value;
    }
    return true;
}

bool agi_runtime_command_json(AgiRuntime *r, const char *text, Error **errp)
{
    static const char *const cycle_fields[] = {"action"};
    static const char *const tick_fields[] = {"action", "ticks"};
    static const char *const input_fields[] = {"action", "text"};
    static const char *const key_fields[] = {"action", "key", "pressed"};
    static const char *const controller_fields[] = {"action", "controller"};
    static const char *const complete_fields[] = {"action", "id", "accepted", "text", "number"};
    static const char *const restore_fields[] = {"action", "id", "snapshot"};
    static const char *const seed_fields[] = {"action", "variables", "flags"};
    g_autofree AgiRuntime *saved = NULL;
    g_autofree uint8_t *snapshot = NULL;
    g_autofree char *native_text = NULL;
    QObject *root;
    QDict *command;
    const char *action;
    uint64_t number = 0, id;
    bool success = false;
    size_t limit = agi_runtime_snapshot_size() * 2 + 8192, length;
    if (!runtime_valid(r, errp)) {
        return false;
    }
    if (!text || (length = strnlen(text, limit + 1)) > limit || !length) {
        error_setg(errp, "AGI_RUNTIME: command is empty or exceeds its bounded JSON extent");
        return false;
    }
    if (!standard_json(text, length, errp)) {
        return false;
    }
    root = qobject_from_json(text, errp);
    if (!root) {
        return false;
    }
    command = qobject_to(QDict, root);
    if (!command) {
        error_setg(errp, "AGI_RUNTIME: command must be a JSON object");
        goto out;
    }
    action = text_value(qdict_get(command, "action"), 32, "action", errp);
    if (!action) {
        goto out;
    }
    saved = g_try_new(AgiRuntime, 1);
    if (!saved) {
        error_setg(errp, "AGI_RUNTIME: insufficient memory for command transaction");
        goto out;
    }
    *saved = *r;
    if (!strcmp(action, "cycle")) {
        if (!keys_match(command, cycle_fields, G_N_ELEMENTS(cycle_fields), 1, "cycle", errp)) {
            goto out;
        }
        success = agi_runtime_cycle(r);
    } else if (!strcmp(action, "tick")) {
        if (!keys_match(command, tick_fields, G_N_ELEMENTS(tick_fields), 2, "tick", errp) ||
            !uint_value(qdict_get(command, "ticks"), 4096, &number, "ticks", errp)) {
            goto out;
        }
        if (!number) {
            error_setg(errp, "AGI_RUNTIME: ticks must be in 1..4096");
            goto out;
        }
        success = agi_runtime_tick(r, number);
    } else if (!strcmp(action, "input")) {
        const char *input;
        if (!keys_match(command, input_fields, G_N_ELEMENTS(input_fields), 2, "input", errp)) {
            goto out;
        }
        input = text_value(qdict_get(command, "text"), (AGI_RT_STRING_BYTES - 1) * 3, "input.text", errp);
        if (!input) {
            goto out;
        }
        native_text = utf8_to_agi(input, AGI_RT_STRING_BYTES - 1, errp);
        if (!native_text) {
            goto out;
        }
        success = agi_runtime_input(r, native_text);
    } else if (!strcmp(action, "key")) {
        QBool *pressed;
        if (!keys_match(command, key_fields, G_N_ELEMENTS(key_fields), 3, "key", errp) ||
            !uint_value(qdict_get(command, "key"), 65535, &number, "key", errp)) {
            goto out;
        }
        pressed = qobject_to(QBool, qdict_get(command, "pressed"));
        if (!pressed) {
            error_setg(errp, "AGI_RUNTIME: pressed must be a boolean");
            goto out;
        }
        success = agi_runtime_key(r, number, qbool_get_bool(pressed));
    } else if (!strcmp(action, "controller")) {
        if (!keys_match(command, controller_fields, G_N_ELEMENTS(controller_fields), 2, "controller", errp) ||
            !uint_value(qdict_get(command, "controller"), 255, &number, "controller", errp)) {
            goto out;
        }
        success = agi_runtime_controller(r, number);
    } else if (!strcmp(action, "complete")) {
        const char *reply = NULL;
        QBool *accepted;
        bool accept, has_text = qdict_haskey(command, "text");
        bool has_number = qdict_haskey(command, "number");
        if (!keys_match(command, complete_fields, G_N_ELEMENTS(complete_fields), 3, "complete", errp) ||
            !uint_value(qdict_get(command, "id"), UINT64_MAX, &id, "complete.id", errp)) {
            goto out;
        }
        accepted = qobject_to(QBool, qdict_get(command, "accepted"));
        if (!accepted || !id) {
            error_setg(errp, "AGI_RUNTIME: completion requires a positive id and boolean accepted");
            goto out;
        }
        accept = qbool_get_bool(accepted);
        if (has_text) {
            reply = text_value(qdict_get(command, "text"), (AGI_RT_STRING_BYTES - 1) * 3, "complete.text", errp);
            if (!reply) {
                goto out;
            }
            native_text = utf8_to_agi(reply, AGI_RT_STRING_BYTES - 1, errp);
            if (!native_text) {
                goto out;
            }
            reply = native_text;
        }
        if (has_number && !uint_value(qdict_get(command, "number"), 255, &number, "complete.number", errp)) {
            goto out;
        }
        if (r->state.status != AGI_RT_PENDING || r->state.pending.id != id) {
            error_setg(errp, "AGI_RUNTIME: completion id does not match the current pending effect");
            goto out;
        }
        if ((!accept && (has_text || has_number)) ||
            (has_text && r->state.pending.reply != AGI_RT_REPLY_TEXT) ||
            (has_number && r->state.pending.reply != AGI_RT_REPLY_NUMBER &&
             r->state.pending.reply != AGI_RT_REPLY_MENU) ||
            (accept && r->state.pending.reply == AGI_RT_REPLY_TEXT && !has_text) ||
            (accept && (r->state.pending.reply == AGI_RT_REPLY_NUMBER ||
                        r->state.pending.reply == AGI_RT_REPLY_MENU) && !has_number)) {
            error_setg(errp, "AGI_RUNTIME: completion payload does not match the explicit reply type");
            goto out;
        }
        success = agi_runtime_complete(r, id, accept, reply, number);
    } else if (!strcmp(action, "restore")) {
        const char *hex;
        size_t size;
        if (!keys_match(command, restore_fields, G_N_ELEMENTS(restore_fields), 3, "restore", errp) ||
            !uint_value(qdict_get(command, "id"), UINT64_MAX, &id, "restore.id", errp)) {
            goto out;
        }
        hex = text_value(qdict_get(command, "snapshot"), agi_runtime_snapshot_size() * 2, "snapshot", errp);
        if (!hex) {
            goto out;
        }
        snapshot = decode_hex(hex, agi_runtime_snapshot_size(), agi_runtime_snapshot_size(), &size, "snapshot", errp);
        if (!snapshot) {
            goto out;
        }
        success = id && agi_runtime_restore(r, id, snapshot, size);
    } else if (!strcmp(action, "seed")) {
        bool has_variables = qdict_haskey(command, "variables");
        bool has_flags = qdict_haskey(command, "flags");
        uint8_t variables[256], flags[256];
        if (!keys_match(command, seed_fields, G_N_ELEMENTS(seed_fields), 1, "seed", errp)) {
            goto out;
        }
        if ((!has_variables && !has_flags) || r->state.retired || r->state.pending.id ||
            r->state.cycle_active || r->state.status != AGI_RT_READY) {
            error_setg(errp, "AGI_RUNTIME: seed requires explicit arrays before execution, with no pending/prepared cycle");
            goto out;
        }
        memcpy(variables, r->state.v, sizeof(variables));
        memcpy(flags, r->state.f, sizeof(flags));
        if ((has_variables && !seed_array(qobject_to(QDict, qdict_get(command, "variables")),
                                          variables, 255, "variables", errp)) ||
            (has_flags && !seed_array(qobject_to(QDict, qdict_get(command, "flags")),
                                      flags, 1, "flags", errp))) {
            goto out;
        }
        memcpy(r->state.v, variables, sizeof(variables));
        memcpy(r->state.f, flags, sizeof(flags));
        success = true;
    } else {
        error_setg(errp, "AGI_RUNTIME: unknown command action %s", action);
        goto out;
    }
    if (!success) {
        error_setg(errp, "AGI_RUNTIME: %s rejected by native preconditions (status %s)",
                   action, agi_runtime_status_name(saved->state.status));
    }
out:
    if (!success && saved) {
        /* Core rejected calls do not overwrite already-stored events. Restore
         * every architectural/observer field as an additional boundary guard;
         * uncommitted storage beyond obs_count is not publicly observable. */
        *r = *saved;
    }
    qobject_unref(root);
    return success;
}
