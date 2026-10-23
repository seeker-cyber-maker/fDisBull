# 0.2 change contract

User goal: initial IDA-like information recovery. Identify/parse headers; retain imports, exports, strings and disk/virtual section layout. Recursively walk entry first, then investigate mapped data references and later symbol/export seeds. Deduplicate facts/tasks and resume within explicit budgets until the queue is empty; never call a budget stop stable. Shared target names/representations resolve at query/render time. Preserve unknowns and version isolation.

Root owns model.py, loader.py integration, decoder.py structured reference extension, project.py, cli.py, render.py integration, API tests/docs/version/package. Inspection agent owns inspection.py + test_inspection.py. CHimpREC agent owns chimprec.py + test_chimprec.py. Read-only reviewer owns no files.

0.1 projects migrate without deleting byte versions or annotations. Added metadata may be unavailable for old projects lacking original file bytes; say so. Patching preserves parent metadata; child analysis uses patched bytes. No Windows process attachment or rebuilt import table is claimed by offline recovery. No public repo writes or relicensing authorized.
