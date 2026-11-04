#!/usr/bin/env python3
"""Prepare a source-pinned, opt-in EMC hook patch. No download/build/launch.

Default prints a diff only. --apply changes the caller-selected ScummVM worktree.
The native JSON dispatcher/controller installation is deliberately not supplied
by this stage; an agent-enabled launch must refuse without that owner.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess

UPSTREAM = "750f2373fb100efe08c6444e36b68c01387fc307"
SCRIPT_BLOB = "63dbc824fa739bd9bb2f3b008fff1e4cb7142382"
PATH = "engines/kyra/script/script.cpp"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def instrument(source: str) -> str:
    def add_once(old: str, new: str) -> None:
        nonlocal source
        if source.count(old) != 1:
            raise ValueError("source hook anchor missing or ambiguous: " + old[:70])
        source = source.replace(old, new, 1)

    add_once('#include "common/endian.h"\n', '#include "common/endian.h"\n'
             '#ifdef FDISBULL_KYRA_HOOKS\n'
             '#include "backends/platform/null/kyra_scummvm_hooks.h"\n#endif\n')
    old = '\tCommon::strlcpy(_scriptData->filename, filename, 13);\n'
    add_once(old, old + '#ifdef FDISBULL_KYRA_HOOKS\n'
             '\tFDisBullKyraHooks::loaded(_vm, _scriptData);\n#endif\n')
    old = '\tdelete[] data->text;\n'
    add_once(old, '#ifdef FDISBULL_KYRA_HOOKS\n'
             '\tFDisBullKyraHooks::unloaded(data);\n#endif\n' + old)
    old = '\tscriptStat->sp = EMCState::kStackLastEntry;\n'
    add_once(old, old + '#ifdef FDISBULL_KYRA_HOOKS\n'
             '\tFDisBullKyraHooks::initialized(scriptStat);\n#endif\n')
    old = '\tint16 code = *script->ip++;\n'
    add_once(old, '#ifdef FDISBULL_KYRA_HOOKS\n'
             '\tconst FDisBullKyra::Id fdisbullSpan = FDisBullKyraHooks::before(_vm, script);\n'
             '#endif\n' + old)
    old = '\treturn (script->ip != nullptr);\n'
    add_once(old, '#ifdef FDISBULL_KYRA_HOOKS\n'
             '\tFDisBullKyraHooks::after(fdisbullSpan);\n#endif\n' + old)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scummvm_worktree", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.scummvm_worktree.resolve(strict=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if head != UPSTREAM:
        raise ValueError("ScummVM HEAD differs from the reviewed upstream pin")
    target = root / PATH
    if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("source target must be a regular file inside the selected worktree")
    raw = target.read_bytes()
    if git_blob(raw) != SCRIPT_BLOB:
        raise ValueError("EMC interpreter source differs from the pinned Git blob")
    old = raw.decode("utf-8")
    new = instrument(old)
    here = Path(__file__).resolve().parent
    additions = {
        root / "backends/platform/null/kyra_debug_core.h": (here / "debug_core.h").read_bytes(),
        root / "backends/platform/null/kyra_scummvm_hooks.h": (here / "scummvm_hooks.h").read_bytes(),
    }
    for path in additions:
        if path.exists() or path.is_symlink() or not path.parent.resolve(strict=True).is_relative_to(root):
            raise ValueError("new hook path exists or escapes worktree: " + str(path))
    print("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                     fromfile="a/" + PATH, tofile="b/" + PATH)))
    if not args.apply:
        print("Dry run only. Native RPC owner and backend-yield wiring are still required.")
        return
    created = []
    try:
        for path, content in additions.items():
            with path.open("xb") as stream:
                stream.write(content)
            created.append(path)
        # The exact source was checked before mutation; preserve the original on failure.
        with target.open("wb") as stream:
            stream.write(new.encode("utf-8"))
    except BaseException:
        target.write_bytes(raw)
        for path in created:
            path.unlink()
        raise
    print("Applied opt-in hooks only. No engine was built, launched, or qualified.")


if __name__ == "__main__":
    main()
