# Analysis capability discovery

`fdisbull capabilities` is a projectless, read-only catalog of this imported
copy's native decoding, debugging, C diagnostics and UDL/UIL/UDC boundaries.
It is included in this source line. A matching version string does not by itself
establish release inclusion; use the selected executable's report.

```sh
fdisbull capabilities
fdisbull capabilities --analyze-headless /opt/ghidra/support/analyzeHeadless --lldb /usr/bin/lldb --java /path/to/java
fdisbull request '{"method":"capabilities","params":{}}'
```

The JSON method also works in a `serve --project ...` session without opening
or querying that project. Options select paths for discovery only; they do not
configure later Ghidra or LLDB calls. Pass the appropriate paths explicitly to
those commands. Python callers can use `fdisbull.capabilities.capabilities()`.

## What the report means

The response uses `format: fdisbull-capabilities-1`. The CLI wraps it in the
normal `{ok, result}` protocol. It contains:

| Field | Interpretation |
| --- | --- |
| `package.runtime_version` | Version of the imported package. |
| `package.distribution_version` | Installed distribution metadata, if present; this can refer to a different installed copy when source overrides it. |
| `package.imported_from` | Directory actually supplying this report. |
| `package.source_revision` | Null: this package has no embedded build commit. No Git or network command is run to guess one. |
| `package.release_status` | `not_determined`; no release certification from a version string. |
| `package.provider_fingerprint`, `sources` | SHA-256 identity of a fixed provider-file inventory. It is neither a whole-repository digest nor a release/working-tree certificate. |
| `dependencies` | Allowlisted Python module presence/metadata, executable-file detection, or an unselected backend configuration. |
| `capabilities` | Per-feature architecture, implementation scope, maturity, interfaces, providers, requirements, discovery availability and runtime-validation status. |
| `discovery` | No target, external tool or native Python dependency was executed/imported by discovery. |

Each capability has three separate dimensions:

- `implementation`: `implemented`, `partial` or `unsupported` describes the
  source's declared feature scope. Even `implemented` does not mean every
  target or input is supported.
- `availability`: `dependencies_detected`, `missing_dependencies`,
  `component_missing`, `host_unsupported`, `not_checked` or `unsupported` is a
  discovery result. The first applicable condition wins in this order:
  unsupported implementation, wrong required host, missing provider file,
  missing dependency, unselected backend, detected dependencies.
- `runtime_validation`: `not_run` for every entry. Executable presence does
  not prove compatibility, a working Java runtime, LLDB Python support, launch
  permission, a compatible guest, or successful native behavior.

`interfaces` uses `cli:` and `python:` prefixes. CLI-only operations such as
`udl-lift-c` are included even though `methods` only lists JSON methods.
The catalog is deliberately scoped; it does not inventory every format parser
or debugger operation. DOS and PE64 backends remain `not_checked` until an
explicitly configured runtime acceptance test is performed elsewhere.
Requirements cover all listed interfaces, including CLI front-end imports;
a direct Python call may require fewer dependencies. A completed acceptance
test elsewhere does not change this command's `not_run` status.

## C and UIL distinctions

| Interface | Actual scope |
| --- | --- |
| `udl-lift-c` | Reads a restricted uint16 C source subset into a model. It does not produce C from a binary. |
| `udl_blocks.asm_to_c` | Produces a restricted statement view from the same straight-line x86-16 lift. It is not an independent decompiler. |
| `ghidra-arm64 --decompile-entry` | Experimental genuine Ghidra C diagnostics for a selected source-bound Mach-O ARM64 function accepted inside a 4 KiB entry window, with time limits. |
| `il-check`, `il-run` | Validate/evaluate primitive `fdisbull-il-1` blocks. Graphics, audio and clicks are planned host events. There is no macOS preferences/IOPM/network host binding. |
| macOS app to UIL / UIL to macOS ARM64 app | General exporter and compiler unsupported. |

The separate x86-16 Ghidra/Reko/DCC draft is not included in this source and
is not reported as an installed engine. A decompiler listing does not recover
SwiftUI views or qualify native-to-UIL correspondence. See
[macOS ARM64 analysis](MACOS_ARM64_ANALYSIS.md) and the
[app replication case study](MACOS_APP_REPLICATION.md).

## Cost and verification

Discovery imports only the standard library and package version. It queries
top-level module specs and distribution metadata without importing native
modules, checks an allowlisted set of paths, and reads at most 2 MiB per fixed
provider file. There is no disk traversal, target load, FDB access, GUI action,
process enumeration, tool version subprocess, preference write or network call.
Ordinary CLI output-size policy still applies if caller-supplied paths or an
explicitly reduced inline limit require retaining a large reply.

Run `python -m pytest -q tests/test_capabilities.py` for CLI/JSON equivalence,
projectless dispatch, a fresh `python -S` process, absence of native imports and
subprocess calls, missing or fake tools, host restrictions, source drift and
invalid arguments. Distribution gates require the module, guides and tests.
Use `doctor` only when an explicit runtime acceptance test is intended.

The default catalog has a tested 32 KiB regression budget, leaving headroom
within the ordinary 64 KiB inline-response limit. This is a default-size check,
not a protocol ceiling or a guarantee for arbitrary caller-supplied paths; the
ordinary output-size policy still applies.
