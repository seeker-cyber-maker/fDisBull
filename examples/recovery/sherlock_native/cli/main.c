/* Thin executable-location adapter. The embeddable JSON command implementation
 * itself uses only ISO C and the shared puzzle logic. No AppKit is linked. */
#if !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "sherlock_cli.h"
#include <stdio.h>
#include <string.h>

#if defined(__APPLE__)
#include <mach-o/dyld.h>
#elif defined(__linux__)
#include <unistd.h>
#endif

int main(int argc, char **argv) {
    char executable[4096];
    char resources[4096];
    const char *resource_directory = NULL;
    int found = 0;

#if defined(__APPLE__)
    uint32_t size = (uint32_t)sizeof executable;
    found = _NSGetExecutablePath(executable, &size) == 0;
#elif defined(__linux__)
    ssize_t size = readlink("/proc/self/exe", executable, sizeof executable - 1u);
    if (size > 0 && (size_t)size < sizeof executable - 1u) {
        executable[size] = '\0';
        found = 1;
    }
#endif
    if (!found && argc > 0 && argv && argv[0] &&
        strlen(argv[0]) < sizeof executable) {
        memcpy(executable, argv[0], strlen(argv[0]) + 1u);
        found = 1;
    }
    if (found) {
        char *slash = strrchr(executable, '/');
        if (slash) {
            int length;
            *slash = '\0';
            length = snprintf(resources, sizeof resources, "%s/../Resources", executable);
            if (length >= 0 && (size_t)length < sizeof resources)
                resource_directory = resources;
        }
    }
    return sh_cli_main(argc, argv, resource_directory);
}
