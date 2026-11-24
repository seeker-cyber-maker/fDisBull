"""Offline replay for opt-in stopped paged LE tracking traces."""

from types import SimpleNamespace
import json

from .event_search import _artifact, _capture_sequence
from .qemu_paged_le_capture import (
    _cpu, _ram_limits, _ram_extent, _compatible_producer, _supports_extended_walks,
    _supports_high_ram, MAX_WITNESS_BYTES, MAX_WITNESS_ROWS,
)
from .qemu_paged_le_observation import replay
from .qemu_dos_source_admission import _source
from .qemu_paged_le_tracking import _paged_producer
from .qemu_runtime_capture import _qemu_input_hashes


def analyze_trace(project, artifact):
    """Revalidate retained stopped witnesses; unknown stops remain unknown."""
    from .le import load_runtime_le_carrier

    try:
        row, doc = _artifact(project, artifact, 'trace')
        meta = json.loads(row['run_metadata'])
        selected = project.version(row['version'])
        binding = doc['binding']
        receipt = doc['binding_artifact']
        if not isinstance(receipt, dict):
            raise ValueError('Paged LE binding requires its complete artifact receipt')
        binding_id = receipt['artifact']
        brow, bdoc = _artifact(project, binding_id, 'dos-source-binding')
        epoch = binding['capture_epoch']
        current_producer = _paged_producer()
        if (
            doc['format'] != 'fdisbull-paged-le-trace-1'
            or bdoc != dict(format='fdisbull-paged-le-tracking-binding-1', recipe=binding)
            or brow['run'] != row['run']
            or brow['version'] != row['version']
            or binding['run'] != row['run']
            or binding['version'] != row['version']
            or binding['version_sha256'] != selected['sha256']
            or binding['source_sha256'] != project.meta['source_sha256']
            or meta['backend'] != 'qemu-dos'
            or meta['source_sha256'] != binding['source_sha256']
            or meta['version_sha256'] != selected['sha256']
            or not isinstance(epoch, str)
            or not epoch.startswith(row['run'] + ':process:')
            or not epoch[len(row['run'] + ':process:') :].isdigit()
            or int(epoch[len(row['run'] + ':process:') :]) < 1
            or not _compatible_producer(doc['producer'], current_producer, tracking=True)
            or doc['native_inputs'] != _qemu_input_hashes(meta['runtime_inputs'])
            or _capture_sequence(project, brow) >= _capture_sequence(project, row)
        ):
            raise ValueError('Paged LE trace identity or binding receipt differs')
        if (
            receipt.get('artifact') != brow['id']
            or any(
                receipt.get(k) != brow[k] for k in ('run', 'version', 'kind', 'sha256', 'size', 'name')
            )
            or receipt.get('metadata') != json.loads(brow['metadata'])
        ):
            raise ValueError('Paged LE binding artifact reference differs')
        source, identity = _source(
            SimpleNamespace(project=project, version=selected, metadata=meta), binding['source_sha256']
        )
        if any(binding[k] != v for k, v in identity.items()):
            raise ValueError('Paged LE source identity differs')
        image = load_runtime_le_carrier(source)
        end, high_end = _ram_limits(meta['machine_configuration'])
        if binding.get('high_ram_end') != high_end or (
            high_end is not None and not _supports_high_ram(doc['producer'], current_producer)
        ):
            raise ValueError('Paged LE trace RAM topology differs from binding or producer')
        events = doc['events']
        if not isinstance(events, list) or len(events) > 10000:
            raise ValueError('Invalid paged LE trace event count')
        if not events and not doc.get('error'):
            raise ValueError('Empty paged LE trace has no recorded error')
        result = []
        for index, event in enumerate(events, 1):
            if event['sequence'] != index:
                raise ValueError('Paged LE trace sequence differs')
            q, mapping, witness = (event[k] for k in ('qualification', 'mapping_identity', 'witness'))
            if q['qualified'] is False:
                if (
                    mapping is not None
                    or witness is not None
                    or q['source_location'] is not None
                    or q['context'] is not None
                    or q['instruction_size'] is not None
                    or q['source_instruction_sha256'] is not None
                    or q['execution_bytes'] != ''
                ):
                    raise ValueError('Unknown event contains source identity')
                result.append(
                    dict(
                        sequence=index,
                        registers=event['registers'],
                        qualification=q,
                        mapping_identity=None,
                    )
                )
                continue
            if q['qualified'] is not True or not isinstance(witness, dict):
                raise ValueError('Invalid paged LE qualification')
            rows = witness['reads']
            if not isinstance(rows, list) or len(rows) > MAX_WITNESS_ROWS:
                raise ValueError('Paged LE witness row budget exceeded')
            total = 0
            for item in rows:
                a, n, h, space = (item[k] for k in ('address', 'length', 'hex', 'space'))
                if (
                    type(a) is not int
                    or type(n) is not int
                    or n <= 0
                    or (space == 'virtual' and not 0 <= a < a + n <= 2**32)
                    or n > 524288
                    or space not in ('physical', 'virtual')
                    or not isinstance(h, str)
                    or len(h) != n * 2
                    or (space == 'physical' and not _ram_extent(a, n, end, high_end))
                ):
                    raise ValueError('Invalid paged LE witness row')
                total += n
                if total > MAX_WITNESS_BYTES:
                    raise ValueError('Paged LE witness byte budget exceeded')
            if _cpu(event['registers'], witness['context']) != witness['cpu']:
                raise ValueError('Paged LE CPU witness differs')
            checked = replay(
                image, row['version'], witness,
                legacy_producer=not _supports_extended_walks(doc['producer']),
                qemu_image_sha256=doc['native_inputs'].get('qemu_image'), high_ram_end=high_end,
            )
            if (
                not checked['qualification']['qualified']
                or checked['qualification'] != q
                or checked['mapping_identity'] != mapping
                or checked['witness'] != witness
            ):
                raise ValueError('Paged LE stopped observation replay differs')
            result.append(
                dict(
                    sequence=index,
                    registers=event['registers'],
                    qualification=q,
                    mapping_identity=mapping,
                )
            )
        return dict(
            artifact=artifact,
            artifact_sha256=row['sha256'],
            run=row['run'],
            source_version=row['version'],
            binding_id=binding['binding_id'],
            outcome=doc['outcome'],
            error=doc.get('error'),
            events=result,
            scope='replayed stopped observations; unknown stops and process lifetime remain unknown',
        )
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError('Malformed paged LE tracking trace') from error
