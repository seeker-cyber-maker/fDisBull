# fDisBull 0.2 acceptance contract

Provide a local agent-first initial auto-analysis tool: identify/parse headers, imports, exports, strings and virtual/disk section layout; recursively follow the entry point; queue referenced memory for investigation; admit later symbol/export seeds; repeat until implemented rules have no pending work. Resource-limited results must remain explicitly incomplete.

The database preserves bytes and versions. Names and representations belong to addresses and are resolved by all referring queries and exports. Representation changes invalidate derived facts and trigger bounded reanalysis; renames do not rewrite instruction text. Imported binaries are never executed.

Static PE descriptor parsing and CHimpREC-derived captured-IAT recovery are separate operations. Recovery uses supplied runtime export evidence, retains aliases/unknowns and does not attach to Windows or rebuild executables.

Verify real ELF import, constructed PE and ARM64 Mach-O metadata, recursive code/data discovery, shared renaming, representation retraction, stable/idempotent resumption, original-input removal/restart, schema-1 migration and version isolation. PNG/SVG exports must use stored state and protect project databases.

Identification of DOS MZ is supported; segmented MZ loading/disassembly is not. Do not claim full DinoPark analysis, macOS runtime verification, full CFG/function boundaries, decompilation, unrestricted data-flow recovery or runtime SMC capture.
