"""Exact native-build identities and fail-closed payload validation (never tests).

Actions provides ref isolation; workflow namespaces additionally prevent promotion
of PR/feature-branch executables to trusted main/tag/manual consumers.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def python_build_packages():
    packages = {}
    for name in ("pip", "setuptools", "distlib", "meson", "ninja", "packaging", "wheel"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return packages


def identity(root, backend, profile, probe=None):
    def command(args):
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
    probe = probe or command
    inputs = [".github/ci/native-build.sh", ".github/ci/native_cache.py"]
    if backend == "dosbox":
        inputs += [f"{profile}/source-manifest.json", f"{profile}/headless-agent.patch"]
    return {
        "schema": 1, "backend": backend, "profile": profile,
        "inputs": {p: digest((root / p).read_bytes()) for p in inputs},
        "os": platform.system(), "architecture": platform.machine(),
        "os_release": Path("/etc/os-release").read_text(),
        "runner_image": os.environ.get("ImageVersion", "unknown"),
        "workspace": str(root.resolve()), "python": sys.version,
        "python_build_packages": python_build_packages(),
        # Full package identities include headers, transitive libraries, build tools,
        # and runtime ABI. No fallback to an older toolchain/dependency inventory.
        "packages": probe(["dpkg-query", "-W", "-f=${Package}=${Version}\\n"]),
        "compiler": probe(["g++", "-v"]),
        "linker": probe(["ld", "--version"]),
        "build_environment": {k: os.environ.get(k, "") for k in (
            "CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LIBS",
            "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "CONFIG_SITE", "PATH",
            "LD_LIBRARY_PATH", "LD_PRELOAD", "LIBRARY_PATH", "CPATH",
            "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "AR", "AS", "RANLIB")},
        "tools": {name: {"path": str(Path(path).resolve()),
                         "sha256": digest(Path(path).read_bytes())}
                  for name in ("cc", "c++", "gcc", "g++", "ld", "make", "ninja",
                               "pkg-config", "autoconf", "automake", "nasm")
                  if (path := shutil.which(name))},
    }


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in cache: {path}")
        if path.name == "receipt.json" and path.parent == directory:
            continue
        if path.is_dir():
            continue
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"Nonregular cache member: {path}")
        result[path.relative_to(directory).as_posix()] = {
            "sha256": digest(path.read_bytes()), "mode": stat.S_IMODE(mode),
            "size": path.stat().st_size,
        }
    if not result:
        raise ValueError("Empty cache")
    return result


def runtime_libraries(binary):
    # Called only after payload digests/ELF headers pass. Nothing from the cache
    # is executed as root; reference isolation supplies the executable trust boundary.
    result = subprocess.run(["ldd", str(binary.resolve())], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or "not found" in result.stdout:
        raise ValueError("Unresolved native runtime libraries: " + result.stdout)
    libraries = {}
    for line in result.stdout.splitlines():
        match = re.search(r"(/\S+)\s+\(", line)
        if match:
            path = Path(match.group(1))
            libraries[str(path)] = digest(path.read_bytes())
    if not libraries:
        raise ValueError("Missing dynamic library inventory")
    return libraries


def check_required(directory, expected):
    executable = "dosbox-x" if expected["backend"] == "dosbox" else "qemu-system-x86_64"
    binary = directory / executable
    if not binary.is_file() or not os.access(binary, os.X_OK) or binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("Missing ELF executable")
    if expected["backend"] == "qemu" and not (directory / "pc-bios/bios-256k.bin").is_file():
        raise ValueError("Missing QEMU firmware")


def seal(directory, expected):
    files = inventory(directory)
    check_required(directory, expected)
    executable = "dosbox-x" if expected["backend"] == "dosbox" else "qemu-system-x86_64"
    receipt = {"identity": expected, "files": files,
               "runtime_libraries": runtime_libraries(directory / executable),
               "producer": {key: os.environ.get(key, "local") for key in (
                   "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_EVENT_NAME", "GITHUB_RUN_ID")}}
    (directory / "receipt.json").write_bytes(canonical(receipt) + b"\n")


def validate(directory, expected):
    try:
        if directory.is_symlink():
            raise ValueError("Symlink cache root")
        files = inventory(directory)
        receipt = json.loads((directory / "receipt.json").read_text())
        if receipt["identity"] != expected or receipt["files"] != files:
            raise ValueError("Identity or file digest mismatch")
        # Recheck the required members, not only those listed in the receipt.
        check_required(directory, expected)
        executable = "dosbox-x" if expected["backend"] == "dosbox" else "qemu-system-x86_64"
        if receipt["runtime_libraries"] != runtime_libraries(directory / executable):
            raise ValueError("Runtime library ABI/digest mismatch")
        return True
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Native cache rejected: {exc}", file=sys.stderr)
        if directory.is_symlink():
            directory.unlink()
        elif directory.exists():
            shutil.rmtree(directory)
        return False


def output(key, value):
    print(f"{key}={value}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"{key}={value}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("key", "validate", "seal"))
    parser.add_argument("backend", choices=("dosbox", "qemu"))
    parser.add_argument("--profile", default="qemu-9.2.4")
    args = parser.parse_args()
    root = Path.cwd()
    expected_path = root / f".native-{args.backend}-identity.json"
    directory = root / ".native-cache" / args.backend
    if args.action == "key":
        if os.environ.get("NATIVE_COLD_CACHE") == "true":
            if directory.is_symlink():
                directory.unlink()
            elif directory.exists():
                shutil.rmtree(directory)
        expected = identity(root, args.backend, args.profile)
        expected_path.write_bytes(canonical(expected))
        output("key", f"native-v1-{args.backend}-{digest(canonical(expected))}")
    else:
        expected = json.loads(expected_path.read_text())
        if args.action == "seal":
            seal(directory, expected)
        else:
            output("valid", str(validate(directory, expected)).lower())


if __name__ == "__main__":
    main()
