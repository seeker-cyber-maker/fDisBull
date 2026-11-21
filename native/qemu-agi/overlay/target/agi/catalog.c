/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/cutils.h"
#include "qapi/error.h"
#include "cpu.h"

/* FDBAGIV1: horizon/reserved/u16 count, then sorted id/u8 loop count/SHA256,
 * with each loop's u8 cel count followed by width/height byte pairs.
 * Catalogs attest metadata identities; they are not original resource payloads.
 */
bool agi_load_view_catalog(AgiCPU *cpu, const char *filename, Error **errp)
{
    g_autofree uint8_t *data = g_malloc(AGI_CATALOG_MAX_BYTES + 1);
    g_autofree char *digest = NULL;
    AgiViewCatalog *catalog = NULL;
    FILE *file;
    struct stat st;
    size_t size, at;
    unsigned i, j, k, count, view_cels;
    int fd, previous = -1;

    if (cpu->catalog) {
        error_setg(errp, "AGI_VIEW_CATALOG: catalog is immutable");
        return false;
    }
    fd = open(filename, O_RDONLY | O_NONBLOCK);
    if (fd < 0) {
        error_setg_errno(errp, errno, "AGI_VIEW_CATALOG: cannot open catalog");
        return false;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size < 12 ||
        st.st_size > AGI_CATALOG_MAX_BYTES) {
        close(fd);
        error_setg(errp, "AGI_VIEW_CATALOG: expected a bounded regular file");
        return false;
    }
    file = fdopen(fd, "rb");
    if (!file) {
        int saved_errno = errno;
        close(fd);
        error_setg_errno(errp, saved_errno, "AGI_VIEW_CATALOG: cannot read catalog");
        return false;
    }
    size = fread(data, 1, AGI_CATALOG_MAX_BYTES + 1, file);
    if (ferror(file) || size < 12 || size > AGI_CATALOG_MAX_BYTES) {
        fclose(file);
        error_setg(errp, "AGI_VIEW_CATALOG: invalid catalog extent");
        return false;
    }
    fclose(file);
    if (memcmp(data, "FDBAGIV1", 8) || data[8] > 167 || data[9] != 0) {
        error_setg(errp, "AGI_VIEW_CATALOG: invalid header or horizon");
        return false;
    }
    count = data[10] | ((unsigned)data[11] << 8);
    if (count == 0 || count > 256) {
        error_setg(errp, "AGI_VIEW_CATALOG: invalid view count");
        return false;
    }
    catalog = g_new0(AgiViewCatalog, 1);
    catalog->size = size;
    catalog->horizon = data[8];
    catalog->view_count = count;
    at = 12;
    for (i = 0; i < count; i++) {
        AgiCatalogView *view;
        unsigned id, loops;
        if (size - at < 34) {
            goto invalid;
        }
        id = data[at++];
        loops = data[at++];
        if ((int)id <= previous || !loops ||
            loops > AGI_CATALOG_MAX_LOOPS - catalog->loop_count) {
            goto invalid;
        }
        previous = id;
        view = &catalog->views[id];
        view->present = true;
        view->first_loop = catalog->loop_count;
        view->loop_count = loops;
        for (j = 0; j < 32; j++) {
            g_snprintf(view->source_sha256 + 2 * j, 3, "%02x", data[at++]);
        }
        view_cels = 0;
        for (j = 0; j < loops; j++) {
            AgiCatalogLoop *loop;
            unsigned cels;
            if (at == size) {
                goto invalid;
            }
            cels = data[at++];
            if (cels > 1024 - view_cels ||
                cels > AGI_CATALOG_MAX_CELS - catalog->cel_count ||
                size - at < 2 * cels) {
                goto invalid;
            }
            view_cels += cels;
            loop = &catalog->loops[catalog->loop_count++];
            loop->first_cel = catalog->cel_count;
            loop->cel_count = cels;
            for (k = 0; k < cels; k++) {
                AgiCatalogCel *cel = &catalog->cels[catalog->cel_count++];
                cel->width = data[at++];
                cel->height = data[at++];
                if (!cel->width || cel->width > 160 ||
                    !cel->height || cel->height > 168) {
                    goto invalid;
                }
            }
        }
    }
    if (at != size) {
        goto invalid;
    }
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, data, size);
    pstrcpy(catalog->sha256, sizeof(catalog->sha256), digest);
    cpu->catalog = catalog;
    cpu->env.binding_profile = 1;
    cpu->env.horizon = catalog->horizon;
    return true;
invalid:
    g_free(catalog);
    error_setg(errp, "AGI_VIEW_CATALOG: malformed topology, dimensions or budget");
    return false;
}
