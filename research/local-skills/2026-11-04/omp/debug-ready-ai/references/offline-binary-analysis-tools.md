# Offline Binary Analysis Tool Roster

Updated: 2026-08-13

Use this roster when `debug-ready-ai` needs source-free anchors before or
alongside LLDB. Choose the smallest analyzer that can answer the current
branch. Static output is evidence, not runtime proof; confirm consequential
claims against the current target and record only useful anchors in
`debug-target-records.md`.

## Selection ladder

| Need | Preferred route | Local status |
| --- | --- | --- |
| File identity, slices, strings, imports, symbols, sections | `rz-bin`, `rabin2`, Apple CLI tools | Qualified first pass |
| Focused function/control-flow inspection | `rizin`, `r2` | Qualified, load after an anchor exists |
| Decompilation, xrefs, recovered types, whole-program flow | Ghidra headless | Qualified bounded static route |
| Live process state, registers, breakpoints, memory | LLDB/lldb-dap | Default runtime route; pass `debug-ready-ai` first |
| IDA database/client or Hex-Rays remote debugging | IDA Pro | Conditional; current client/license path must be qualified |

Do not run every analyzer as a ritual. Escalate only when the next tier is the
cheapest decisive evidence or provides a useful independent second opinion.

## Installed paths and qualification

- Rizin 0.9.1: `/opt/homebrew/bin/rizin`, `/opt/homebrew/bin/rz-bin`,
  `/opt/homebrew/bin/rz-asm`
- radare2 6.1.8: `/opt/homebrew/bin/r2`, `/opt/homebrew/bin/rabin2`
- Ghidra 12.1.2:
  - GUI launcher: `/opt/homebrew/bin/ghidraRun`
  - headless analyzer:
    `/opt/homebrew/Cellar/ghidra/12.1.2/libexec/support/analyzeHeadless`
  - `analyzeHeadless` is not currently on `PATH`; use the explicit path or
    rediscover it through Homebrew before use.
- LLVM runtime debugging:
  - `/opt/homebrew/opt/llvm/bin/lldb`
  - `/opt/homebrew/opt/llvm/bin/lldb-dap`
- IDA Professional 9.4: `/Applications/IDA Professional 9.4.app`
  - remote server:
    `/Applications/IDA Professional 9.4.app/Contents/MacOS/dbgsrv/mac_server_arm`
  - the server speaks Hex-Rays' proprietary protocol, not DAP or LLDB.
  - require loopback or an explicitly approved interface, TLS/password, and a
    qualified licensed IDA client. The installed client/license route was not
    qualified in the last recorded check, so it is not a default analyzer.

Versions and entitlement state drift. Recheck paths and qualification cheaply
when a task actually selects the tool.

## Cheap first-pass commands

### Universal/fat Mach-O slices

```sh
rz-bin -A <binary>
rabin2 -A <binary>
```

Record architecture, slice offsets, and which slice matches the live process.

### Binary metadata

```sh
rz-bin -I -j <binary>
rabin2 -I -j <binary>
```

Useful fields include `arch`, `bits`, `bintype`, `lang`, `stripped`, `pic`,
`baddr`, `binsz`, and `compiler`. These fields describe the analyzed bytes;
they do not need a new hash unless exact identity across a handoff matters.

### Strings

```sh
rz-bin -zz -j <binary>
rabin2 -zz -j <binary>
```

For a meaningful string hit, keep the containing string, virtual address,
physical/file offset semantics, section, encoding, and selected slice. For a
universal Mach-O, verify any file offset that will be reused; tools may report
offsets relative to different views or slices.

### Imports, libraries, symbols, and classes

```sh
rz-bin -i -j <binary>
rz-bin -l <binary>
rz-bin -s -j <binary>
rz-bin -c <binary>
rabin2 -i -j <binary>
rabin2 -l <binary>
rabin2 -s -j <binary>
rabin2 -c <binary>
```

Function, API, selector, and class names often explain why a string exists
faster than broad decompilation.

## Bounded Ghidra route

Choose Ghidra when the active branch needs xrefs, a decompiler view, recovered
types, call relationships, or whole-program flow that the cheaper tools cannot
settle. Keep the run target-scoped:

1. identify the exact binary and architecture/slice;
2. use a dedicated disposable or project-owned analysis directory;
3. import only the target and load only scripts required for the question;
4. capture the relevant function/address/xref facts rather than dumping the
   full decompiler database into model context;
5. corroborate consequential static claims with source, a second static tool,
   a controlled test, or LLDB when runtime behavior matters.

Ghidra previously provided useful independent evidence for a local app by
recovering a Cloud Run URL and confirming an encrypted Mach-O range already
seen by Rizin. That qualifies the route as useful, not every decompiler
interpretation as correct.

## Conditional IDA route

Do not reject IDA merely because LLDB is the default, but do not overstate its
current readiness:

- IDA can add decompiler/database context and a remote debugging route when a
  valid licensed client is available.
- `mac_server_arm` is not a drop-in DAP adapter. An LLDB-DAP client cannot use
  it directly.
- Bind remote debugging to loopback unless the user explicitly authorizes a
  network exposure; use the server's authentication and transport protections.
- Re-qualify the IDA application, entitlement/license, client-to-server
  handshake, exact target identity, and one non-destructive smoke check before
  marking it operational.
- Until that gate passes, use Rizin/Ghidra for static work and LLDB/lldb-dap for
  runtime work. Never attempt to bypass IDA licensing.

## Prior reproducible sample

For `/tmp/NotepadX-debug.app/Contents/MacOS/NotepadX`, the installed cheap tools
previously established:

- `rz-bin -A` reported x86_64 at offset `0x4000` and arm64 at `0xf0000`.
- `rz-bin -I -j` identified a 64-bit Darwin Swift Mach-O.
- `rz-bin -zz -j` found the containing string for `curated fallback chain` at
  virtual address `0x100093ec0`, physical offset `1588928`.
- Direct byte search confirmed the string in both universal-binary slices.
- `rabin2 -zz -j` placed it in `4.__TEXT.__cstring`.

Conclusion: the phrase was shipped NotepadX settings copy about non-Latin font
fallback, not a generated skill name.

## Reporting

Do not dump raw analyzer JSON or whole decompiler output into the user answer.
Distill it through `tell-story-ai`:

```text
Story: <what the object is and why it exists>
Where: <binary/slice/section/address or source/resource>
Clues: <functions/imports/API/selector names if useful>
Confidence: <confirmed/likely/static-only> because <short evidence>
```
