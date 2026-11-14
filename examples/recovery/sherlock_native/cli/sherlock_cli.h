#ifndef SHERLOCK_CLI_H
#define SHERLOCK_CLI_H
#include <stddef.h>
#include "../core/sherlock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Normal main-style argv: argv[0] is the executable/dispatch name. The caller
 * owns all arguments; this function never changes them or exits the process.
 * resource_directory, when supplied, contains sherlock_puzzles.bin. Native
 * generated puzzles need no resource files. One JSON response goes to stdout.
 * See README.md for the protocol, path precedence and exit-code contract. */
int sh_cli_main(int argc, char **argv, const char *resource_directory);

/* The native UI can copy precisely the identity used by the JSON interface.
 * native_generator is 0 for an original numbered puzzle, 1 for the current
 * native generator/version and supplied full seed. Only public fields enter
 * the fingerprint. Return 0 on success, -1 on invalid public fields/arguments
 * or insufficient capacity. Failure leaves output unchanged. */
int sh_cli_format_challenge_id(const SherlockPuzzle *puzzle,
                              int native_generator, uint64_t seed,
                              char *output, size_t capacity);

#ifdef __cplusplus
}
#endif
#endif
