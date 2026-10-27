# Structural DOS executable recognition and guest names

Unreleased source change after published 0.18.0. The existing 0.18.0 packages
and shared system installation retain their recorded filename limitation.

The loader identifies a DOS MZ image by parsing its bytes and header, regardless
of the host filename. A file named `AGI`, a long filename, or an unexpected
suffix is eligible when its structure is a supported MZ executable. An `.EXE`
suffix alone never makes an unsupported file eligible. Raw COM/SYS detection
is not added by this change; non-self-identifying raw inputs still need an
explicit format/profile.

The DOS launcher needs a guest name its shell can execute. Safe 8.3 `.EXE` and
`.COM` names remain unchanged. Other names use a deterministic `FBxxxxxx.EXE`
alias derived from the original source digest. The project retains the original
filename, source bytes, source hash, mapped instruction identities and every
static version. Runtime metadata records `source_filename`, the guest `target`
and `target_aliased`. The alias contains exactly the original executable bytes.

## Direct DOSBox

The session exclusively creates one temporary alias beside the executable in
the mounted game directory. It needs write permission for that directory. This
keeps the current directory and neighboring resource/save paths unchanged,
without copying or relocating the resource tree. Existing input files are not
renamed or overwritten. Case-insensitive name collisions reject launch before
spawning; existing aliases are never adopted merely because their bytes match.

The alias participates in the mounted-file checkpoint manifest. A later session
recreates the same alias before restoring a checkpoint, so hash checks and
resource access retain the same namespace. Mounted file rollback is still not
part of native restoration.

Normal close and failed startup remove an unchanged owned alias. Completed
changes or replacements detected during cleanup are retained and recorded as
`retained_changed` in the close event, preserving possible output. A forcibly
killed controller can also leave an alias behind; inspect it before removing or
moving it. The next launch rejects that collision rather than deleting it.
Cleanup parks the alias atomically in a private `.fdisbull-alias-*` directory
before rechecking its identity. If a replacement wins that race, it is restored
without overwriting a new pathname, or retained in that directory with its path
recorded in the close event. Such retained output is never auto-deleted.
The alias is a disposable launch copy, not a user output/editing surface.
Concurrent external writes through open handles during teardown are unsupported;
the emulator is reaped before cleanup. Original source files are never removed.

## DOS-in-QEMU

Only explicitly selected host files are uploaded. The executable alias is added
inside the disposable guest; no host alias is created. The original guest name
is also retained when it passes the upload path/exclusion rules. A structurally
validated MZ target named with a state/database-like suffix is uploaded only
under its executable alias. Other saved states and project databases remain
excluded. Guest file manifests include the alias and native restoration checks
them as before. The final upload, including alias bytes, must fit the 1,024-file
and 64 MiB limits before QEMU starts. No new guest runtime or DOSBox binary is
required.

## Verification scope

Authored MZ guests cover extensionless, long/space-containing and unexpected
suffix names. Direct checks read a neighboring resource through DOS, stop at a
disassembly breakpoint, save real screenshots and bounded traces, close/reopen
the project and emulator, and restore the native checkpoint. The original
executable/resource bytes remain unchanged and ordinary aliases disappear on
close. Negative cases cover collisions, changed-output preservation, failed
transport cleanup and continued exclusion of unrelated private state assets.
Separate DOS-in-QEMU checks exercise extensionless/long target aliases, native
save/restore, breakpoints, screenshots and traces without a host alias.

These are executable-format and debugger checks using redistributable authored
fixtures. They do not claim a Police Quest/AGI game replay or an AGI script
decoder implementation.

[Verification and limits](VERIFICATION-DOS-CAPTURE-UNRELEASED.md) retain the
authored native results and source hashes separately from published 0.18.0.
