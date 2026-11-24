/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qobject/qdict.h"
#include "qobject/qjson.h"
#include "qobject/qlist.h"
#include "qobject/qnum.h"
#include "qobject/qstring.h"
#include "resources.h"

#define SCUMM_MANIFEST_MAX (2u * 1024u * 1024u)
#define SCUMM_RESOURCE_MIN 4u
#define SCUMM_RESOURCE_MAX 65535u
#define SCUMM_BANK_MAX (64u * 1024u * 1024u)

static const char *const resource_names[SCUMM_RESOURCE_TYPES] = {
    "costume", "room", "script", "sound",
};

void scumm_resource_bank_free(ScummResourceBank *bank)
{
    unsigned type, id;

    if (!bank) {
        return;
    }
    for (type = 0; type < SCUMM_RESOURCE_TYPES; type++) {
        for (id = 0; id < SCUMM_RESOURCE_SLOTS; id++) {
            g_free(bank->bytes[type][id]);
        }
    }
    g_free(bank);
}

/* Pin every directory with an fd and refuse links at every step. Relative
 * resource paths have no empty, dot, or parent components. The user-supplied
 * manifest path may have dot components, but never parent components. */
static int open_relative_file(int base_fd, const char *path, bool allow_dot,
                              int *parent_fd, Error **errp)
{
    g_autofree char *copy = NULL;
    char *part, *slash;
    const unsigned char *p;
    int dir_fd = -1, next_fd, fd = -1;

    if (!path || !*path || path[0] == '/' || !g_utf8_validate(path, -1, NULL)) {
        error_setg(errp, "SCUMM resource path must be a nonempty relative path");
        return -1;
    }
    for (p = (const unsigned char *)path; *p; p++) {
        if (*p < 0x20 || *p == 0x7f || *p == '\\') {
            error_setg(errp, "SCUMM resource path contains a forbidden character");
            return -1;
        }
    }
    copy = g_strdup(path);
    /* Validate the entire path before opening any of its components. */
    part = copy;
    do {
        slash = strchr(part, '/');
        if (slash) {
            *slash = 0;
        }
        if (!*part || !strcmp(part, "..") ||
            (!allow_dot && !strcmp(part, "."))) {
            error_setg(errp, "SCUMM resource path has an unsafe component");
            return -1;
        }
        if (slash) {
            *slash = '/';
            part = slash + 1;
        }
    } while (slash);

    dir_fd = openat(base_fd, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC |
                    O_NOFOLLOW);
    if (dir_fd < 0) {
        error_setg_errno(errp, errno, "Cannot open SCUMM resource directory");
        return -1;
    }
    part = copy;
    while ((slash = strchr(part, '/'))) {
        *slash = 0;
        next_fd = openat(dir_fd, part, O_RDONLY | O_DIRECTORY | O_CLOEXEC |
                        O_NOFOLLOW);
        if (next_fd < 0) {
            error_setg_errno(errp, errno,
                             "Cannot traverse SCUMM resource directory");
            goto out;
        }
        close(dir_fd);
        dir_fd = next_fd;
        part = slash + 1;
    }
    /* O_NONBLOCK prevents a FIFO from hanging before fstat rejects it. */
    fd = openat(dir_fd, part, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) {
        error_setg_errno(errp, errno, "Cannot open SCUMM resource file");
        goto out;
    }
    if (parent_fd) {
        *parent_fd = dir_fd;
        dir_fd = -1;
    }
out:
    if (dir_fd >= 0) {
        close(dir_fd);
    }
    return fd;
}

static bool read_regular_file(int fd, size_t minimum, size_t maximum,
                              uint8_t **data, size_t *size, Error **errp)
{
    g_autofree uint8_t *buffer = NULL;
    struct stat st;
    size_t length, done = 0;
    ssize_t count;
    uint8_t extra;

    if (fstat(fd, &st) < 0) {
        error_setg_errno(errp, errno, "Cannot stat SCUMM resource file");
        return false;
    }
    if (!S_ISREG(st.st_mode) || st.st_size < 0 ||
        (uint64_t)st.st_size < minimum || (uint64_t)st.st_size > maximum) {
        error_setg(errp, "SCUMM file must be regular and have size %zu..%zu",
                   minimum, maximum);
        return false;
    }
    length = st.st_size;
    buffer = g_malloc(length + 1);
    while (done < length) {
        count = read(fd, buffer + done, length - done);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0) {
            error_setg_errno(errp, errno, "Cannot read SCUMM resource file");
            return false;
        }
        if (!count) {
            error_setg(errp, "SCUMM file became shorter while reading");
            return false;
        }
        done += count;
    }
    do {
        count = read(fd, &extra, 1);
    } while (count < 0 && errno == EINTR);
    if (count < 0) {
        error_setg_errno(errp, errno, "Cannot finish reading SCUMM file");
        return false;
    }
    if (count) {
        error_setg(errp, "SCUMM file became larger while reading");
        return false;
    }
    buffer[length] = 0;
    *data = g_steal_pointer(&buffer);
    *size = length;
    return true;
}

/* QEMU's JSON parser additionally accepts single-quoted strings and \\'.
 * Exclude those extensions and embedded NULs before calling its parser. */
static bool manifest_json_text(const uint8_t *data, size_t size, Error **errp)
{
    bool string = false, escaped = false;
    size_t i;

    if (memchr(data, 0, size) ||
        !g_utf8_validate((const char *)data, size, NULL)) {
        error_setg(errp, "SCUMM manifest must contain NUL-free UTF-8 JSON");
        return false;
    }
    for (i = 0; i < size; i++) {
        if (escaped) {
            if (data[i] == '\'') {
                error_setg(errp, "SCUMM manifest has a non-JSON string escape");
                return false;
            }
            escaped = false;
        } else if (string && data[i] == '\\') {
            escaped = true;
        } else if (data[i] == '"') {
            string = !string;
        } else if (!string && data[i] == '\'') {
            error_setg(errp, "SCUMM manifest requires JSON double-quoted strings");
            return false;
        }
    }
    return true;
}

static const char *get_string(const QDict *dict, const char *key, Error **errp)
{
    QString *value = qobject_to(QString, qdict_get(dict, key));
    const char *text = value ? qstring_get_str(value) : NULL;

    /* QString represents escaped U+0000 as modified UTF-8; reject it too. */
    if (!text || !g_utf8_validate(text, -1, NULL)) {
        error_setg(errp, "SCUMM manifest '%s' must be a NUL-free UTF-8 string",
                   key);
        return NULL;
    }
    return text;
}

static bool get_uint(const QDict *dict, const char *key, uint64_t minimum,
                     uint64_t maximum, uint64_t *value, Error **errp)
{
    QNum *number = qobject_to(QNum, qdict_get(dict, key));

    if (!number || !qnum_get_try_uint(number, value) ||
        *value < minimum || *value > maximum) {
        error_setg(errp, "SCUMM manifest '%s' must be an integer in "
                   "[%" PRIu64 ", %" PRIu64 "]", key, minimum, maximum);
        return false;
    }
    return true;
}

static const char *get_sha256(const QDict *dict, const char *key, Error **errp)
{
    const char *text = get_string(dict, key, errp);
    size_t i;

    if (!text) {
        return NULL;
    }
    if (strlen(text) == 64) {
        for (i = 0; i < 64; i++) {
            if (!g_ascii_isdigit(text[i]) &&
                !(text[i] >= 'a' && text[i] <= 'f')) {
                break;
            }
        }
        if (i == 64) {
            return text;
        }
    }
    error_setg(errp, "SCUMM manifest '%s' must be a lowercase SHA-256 digest",
               key);
    return NULL;
}

static bool load_resource(QDict *entry, int dir_fd, ScummRuntime *runtime,
                          ScummResourceBank *bank, size_t *total,
                          Error **errp)
{
    g_autofree uint8_t *data = NULL;
    g_autofree char *actual_sha256 = NULL;
    const char *name, *expected_sha256, *path;
    uint64_t id, declared_size;
    size_t size;
    unsigned type;
    int fd;
    bool read_ok;

    name = get_string(entry, "type", errp);
    if (!name) {
        return false;
    }
    for (type = 0; type < SCUMM_RESOURCE_TYPES; type++) {
        if (!strcmp(name, resource_names[type])) {
            break;
        }
    }
    if (type == SCUMM_RESOURCE_TYPES) {
        error_setg(errp, "SCUMM manifest has an unknown resource type");
        return false;
    }
    if (!get_uint(entry, "id", 0, SCUMM_RESOURCE_SLOTS - 1, &id, errp) ||
        !get_uint(entry, "size", SCUMM_RESOURCE_MIN, SCUMM_RESOURCE_MAX,
                  &declared_size, errp)) {
        return false;
    }
    if (id >= runtime->counts[type]) {
        error_setg(errp, "SCUMM resource %s/%" PRIu64 " exceeds its table count",
                   name, id);
        return false;
    }
    if (runtime->resources[type][id].available) {
        error_setg(errp, "SCUMM manifest repeats resource %s/%" PRIu64, name, id);
        return false;
    }
    if (declared_size > SCUMM_BANK_MAX - *total) {
        error_setg(errp, "SCUMM resource bank exceeds 64 MiB");
        return false;
    }
    expected_sha256 = get_sha256(entry, "sha256", errp);
    if (!expected_sha256) {
        return false;
    }
    path = get_string(entry, "path", errp);
    if (!path) {
        return false;
    }
    fd = open_relative_file(dir_fd, path, false, NULL, errp);
    if (fd < 0) {
        error_prepend(errp, "SCUMM resource %s/%" PRIu64 ": ", name, id);
        return false;
    }
    read_ok = read_regular_file(fd, declared_size, declared_size,
                                &data, &size, errp);
    close(fd);
    if (!read_ok) {
        error_prepend(errp, "SCUMM resource %s/%" PRIu64 ": ", name, id);
        return false;
    }
    if (((unsigned)data[0] | ((unsigned)data[1] << 8)) != size) {
        error_setg(errp, "SCUMM resource %s/%" PRIu64
                   " has a mismatched little-endian size header", name, id);
        return false;
    }
    actual_sha256 = g_compute_checksum_for_data(G_CHECKSUM_SHA256, data, size);
    if (strcmp(expected_sha256, actual_sha256)) {
        error_setg(errp, "SCUMM resource %s/%" PRIu64 " SHA-256 mismatch", name, id);
        return false;
    }
    bank->bytes[type][id] = g_steal_pointer(&data);
    g_strlcpy(bank->sha256[type][id], expected_sha256,
              sizeof(bank->sha256[type][id]));
    runtime->resources[type][id].size = size;
    runtime->resources[type][id].available = 1;
    *total += size;
    return true;
}

bool scumm_resource_bank_load(const char *manifest_path,
                             const uint8_t *code, size_t code_size,
                             ScummRuntime *runtime, ScummResourceBank **bank,
                             Error **errp)
{
    ERRP_GUARD();
    g_autofree uint8_t *manifest = NULL;
    g_autofree char *digest = NULL;
    g_autofree ScummRuntime *staged = NULL;
    ScummResourceBank *staged_bank = NULL;
    QObject *object = NULL;
    QDict *dict, *counts, *entry;
    QList *resources;
    const QListEntry *item;
    const char *text, *relative_path;
    uint64_t value;
    size_t manifest_size, total = 0;
    unsigned type;
    int root_fd = -1, dir_fd = -1, manifest_fd = -1;
    bool ok = false;

    if (!manifest_path || !*manifest_path || !runtime || !bank ||
        (!code && code_size) || code_size > SCUMM_CODE_MAX) {
        error_setg(errp, "SCUMM_RESOURCE: Invalid resource bank arguments");
        return false;
    }
    if (*bank) {
        error_setg(errp, "SCUMM_RESOURCE: Resource bank is already loaded");
        return false;
    }
    relative_path = manifest_path;
    if (manifest_path[0] == '/') {
        root_fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        relative_path++;
    } else {
        root_fd = open(".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    }
    if (root_fd < 0) {
        error_setg_errno(errp, errno, "Cannot open SCUMM manifest directory");
        goto out;
    }
    manifest_fd = open_relative_file(root_fd, relative_path, true,
                                      &dir_fd, errp);
    if (manifest_fd < 0 ||
        !read_regular_file(manifest_fd, 1, SCUMM_MANIFEST_MAX,
                           &manifest, &manifest_size, errp) ||
        !manifest_json_text(manifest, manifest_size, errp)) {
        goto out;
    }
    object = qobject_from_json((const char *)manifest, errp);
    if (!object) {
        goto out;
    }
    dict = qobject_to(QDict, object);
    if (!dict) {
        error_setg(errp, "SCUMM resource manifest must be a JSON object");
        goto out;
    }
    text = get_string(dict, "schema", errp);
    if (!text) {
        goto out;
    }
    if (strcmp(text, "fdisbull-scumm-v2-resources-1")) {
        error_setg(errp, "Unsupported SCUMM resource manifest schema");
        goto out;
    }
    text = get_string(dict, "profile", errp);
    if (!text) {
        goto out;
    }
    if (strcmp(text, "amiga-v2-isolated")) {
        error_setg(errp, "SCUMM resource manifest requires amiga-v2-isolated");
        goto out;
    }
    staged = g_new0(ScummRuntime, 1);
    staged_bank = g_new0(ScummResourceBank, 1);
    text = get_sha256(dict, "source_receipt_sha256", errp);
    if (!text) {
        goto out;
    }
    g_strlcpy(staged_bank->source_receipt_sha256, text,
              sizeof(staged_bank->source_receipt_sha256));
    if (!get_uint(dict, "script_id", 1, SCUMM_RESOURCE_SLOTS - 1,
                  &value, errp)) {
        goto out;
    }
    staged->script_id = value;
    text = get_sha256(dict, "code_sha256", errp);
    if (!text) {
        goto out;
    }
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, code, code_size);
    if (strcmp(text, digest)) {
        error_setg(errp, "SCUMM kernel does not match manifest code_sha256");
        goto out;
    }
    g_clear_pointer(&digest, g_free);
    counts = qobject_to(QDict, qdict_get(dict, "counts"));
    resources = qobject_to(QList, qdict_get(dict, "resources"));
    if (!counts || !resources ||
        qlist_size(resources) > SCUMM_RESOURCE_TYPES * SCUMM_RESOURCE_SLOTS) {
        error_setg(errp, "SCUMM manifest requires counts and at most 1024 resources");
        goto out;
    }
    for (type = 0; type < SCUMM_RESOURCE_TYPES; type++) {
        if (!get_uint(counts, resource_names[type], 0, SCUMM_RESOURCE_SLOTS,
                      &value, errp)) {
            goto out;
        }
        staged->counts[type] = value;
    }
    QLIST_FOREACH_ENTRY(resources, item) {
        entry = qobject_to(QDict, qlist_entry_obj(item));
        if (!entry) {
            error_setg(errp, "SCUMM resource entry must be a JSON object");
            goto out;
        }
        if (!load_resource(entry, dir_fd, staged, staged_bank, &total, errp)) {
            goto out;
        }
    }
    if (!staged->resources[S_RES_SCRIPT][staged->script_id].available) {
        error_setg(errp, "SCUMM manifest omits the selected script resource");
        goto out;
    }
    if (staged->resources[S_RES_SCRIPT][staged->script_id].size - 4 != code_size ||
        (code_size && memcmp(staged_bank->bytes[S_RES_SCRIPT][staged->script_id] + 4,
                             code, code_size))) {
        error_setg(errp, "SCUMM kernel differs from selected script resource");
        goto out;
    }
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, manifest,
                                         manifest_size);
    g_strlcpy(staged_bank->manifest_sha256, digest,
              sizeof(staged_bank->manifest_sha256));
    staged->enabled = 1;
    scumm_runtime_reset(staged);

    /* No operation that can fail follows publication of the staged state. */
    *runtime = *staged;
    *bank = staged_bank;
    staged_bank = NULL;
    ok = true;
out:
    if (!ok) {
        error_prepend(errp, "SCUMM_RESOURCE: ");
    }
    if (manifest_fd >= 0) {
        close(manifest_fd);
    }
    if (dir_fd >= 0) {
        close(dir_fd);
    }
    if (root_fd >= 0) {
        close(root_fd);
    }
    qobject_unref(object);
    scumm_resource_bank_free(staged_bank);
    return ok;
}
