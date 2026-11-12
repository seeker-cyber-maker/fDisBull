"""Capture a caller-selected directory into a private C:/D: DOS disk."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from .dos_file_layers import capture_directory, WorkspaceStore
from .dos_workspace_fat import build_volume, build_composite
from .freedos_runtime import resolve_runtime


def prepare_workspace(project, game_dir, directory, mode, runtime, boot_image, staging,
                      generation=None, version_id=None):
    if mode not in (None, 'checkpointed'):
        raise ValueError('Only checkpointed DOS files are qualified; live refresh is unavailable')
    if generation is None:
        root = Path(directory if directory is not None else game_dir).expanduser().resolve(strict=True)
        source = (Path(game_dir).expanduser().resolve(strict=True) / project.meta['filename'])
        try:
            source_relative = source.relative_to(root).as_posix()
        except ValueError:
            raise ValueError('DOS executable must be inside the selected directory workspace') from None
        captured = capture_directory(root)
        item = next((row for row in captured['entries'] if row['path'] == source_relative), None)
    else:
        if directory is not None or mode is not None:
            raise ValueError('A sealed generation supplies its own directory and file mode')
        selected_version = project.version(version_id)
        reader = SimpleNamespace(project=project, version=selected_version, run_id='')
        store = WorkspaceStore(reader)
        loaded = store.load(generation)
        manifest = loaded['manifest']
        base = store.load(manifest['base'] or generation)
        original = next((row for row in base['entries'] if row['type'] == 'file'
                         and row['sha256'] == project.meta['source_sha256']
                         and row['path'].split('/')[-1] == project.meta['filename']), None)
        if original is None:
            raise ValueError('Workspace generation has no matching original project executable')
        item = next((row for row in loaded['entries'] if row['dos_path'] == original['dos_path']), None)
        captured = dict(entries=loaded['entries'], root=manifest['source_root'],
                        root_identity=manifest['source_identity'])
    if (item is None or item['type'] != 'file'
            or hashlib.sha256(item['data']).hexdigest() != project.meta['source_sha256']):
        raise ValueError('Directory workspace executable differs from its original project source')
    if runtime is not None or boot_image is None:
        selected = resolve_runtime(runtime)
        system = Path(selected['image']).read_bytes()
        component = deepcopy(selected['manifest'])
    else:
        system = Path(boot_image).expanduser().resolve(strict=True).read_bytes()
        component = dict(format='caller-owned-freedos-template', size=len(system),
                         sha256=hashlib.sha256(system).hexdigest())
    entries = {row['dos_path']: {key: value for key, value in row.items()
               if key in ('type', 'data', 'attributes', 'dos_date', 'dos_time')}
               for row in captured['entries']}
    disk, layout = build_composite(system, build_volume(entries))
    path = Path(staging) / 'workspace-base.img'
    with path.open('xb') as stream:
        stream.write(disk)
    pinned = Path(staging) / ('source.COM' if project.meta['format'] == 'COM' else 'source.EXE')
    with pinned.open('xb') as stream:
        stream.write(item['data'])
    return dict(capture=captured, image=path, source=pinned,
                target='D:\\' + item['dos_path'], source_dospath=item['dos_path'],
                mode='checkpointed' if mode is None else mode, runtime_component=component,
                layout=layout, generation=generation)
