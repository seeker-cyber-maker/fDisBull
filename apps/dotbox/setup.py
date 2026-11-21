"""Stage reviewed canonical resources into both direct and sdist-built wheels."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


ROOT = Path(__file__).resolve().parent
resource_path = runpy.run_path(str(ROOT / 'native/source_inputs.py'))['resource_path']


def resource_names():
    manifest = json.loads((ROOT / "src/dotbox/resources_manifest.json").read_text())
    names = manifest["files"]
    if manifest["format"] != "dotbox-resource-manifest-1" or len(set(names)) != len(names):
        raise ValueError("Invalid DotBox resource manifest")
    for name in names:
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or ".." in path.parts or
                "\\" in name or str(path) != name):
            raise ValueError("Invalid DotBox resource path: " + name)
    if not set(manifest["topics"].values()) <= set(names):
        raise ValueError("Every guide topic must be a listed resource")
    return names


class BuildWithResources(build_py):
    def run(self):
        super().run()
        if self.dry_run:
            return
        destination = Path(self.build_lib) / "dotbox/resources"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        catalog = {"format": "dotbox-resource-catalog-1", "files": {}}
        for name in resource_names():
            source = resource_path(ROOT, name)
            if (not source.is_file() or
                    any(path.is_symlink() for path in (source, *source.parents) if path != ROOT.parent)):
                raise ValueError("Missing or symlinked DotBox resource: " + name)
            data = source.read_bytes()
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            catalog["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        (destination / "catalog.json").write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")

    def get_outputs(self, include_bytecode=1):
        outputs = super().get_outputs(include_bytecode)
        directory = Path(self.build_lib) / "dotbox/resources"
        return outputs + [str(directory / name) for name in (*resource_names(), "catalog.json")]


class SourceWithResources(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        if self.dry_run:
            return
        destination = Path(base_dir)
        staged = []
        for name in resource_names():
            source = resource_path(ROOT, name)
            target = destination / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                staged.append(name)
        if staged:
            egg_info = Path(self.get_finalized_command('egg_info').egg_info)
            if egg_info.is_absolute():
                egg_info = egg_info.relative_to(ROOT)
            inventory = destination / egg_info / 'SOURCES.txt'
            names = set(inventory.read_text().splitlines()) | set(staged)
            # The release tree may contain hardlinks to checkout metadata.
            inventory.unlink()
            inventory.write_text('\n'.join(sorted(names)) + '\n')


setup(cmdclass={"build_py": BuildWithResources, "sdist": SourceWithResources})
