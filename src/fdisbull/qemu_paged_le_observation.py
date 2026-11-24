"""Fresh, replayable stopped-boundary LE source observations.

The caller must bracket this operation with stopped CPU, owner and source-version
checks. This helper establishes neither process lifetime nor snapshot atomicity.
"""

from copy import deepcopy
from hashlib import sha256

from .dosbox_rpc import DebuggerError
from .qemu_le_translation import translate_linear
from .qemu_paged_le_capture import _interpret, MAX_WITNESS_BYTES, MAX_WITNESS_ROWS


def _unknown(error):
    return dict(
        qualification=dict(
            qualified=False,
            reason=str(error),
            instruction_size=None,
            execution_bytes="",
            source_instruction_sha256=None,
            source_location=None,
            context=None,
        ),
        mapping_identity=None,
        witness=None,
    )


def observe(image, source_version, cpu, context, read_physical, read_virtual):
    """Re-match the current boundary and retain the reads needed for replay.

    A failed observation has no source or mapping identity. Readers must restrict
    access to witnessed ordinary RAM; the caller verifies CPU/context stability.
    """
    rows = {}
    total = 0

    def sample(space, reader, address, length):
        nonlocal total
        key = (space, address, length)
        if key not in rows and (
            type(length) is not int
            or length < 1
            or total + length > MAX_WITNESS_BYTES
            or len(rows) >= MAX_WITNESS_ROWS
        ):
            raise ValueError("Stopped observation read budget exceeded")
        value = reader(address, length)
        if not isinstance(value, bytes) or len(value) != length:
            raise ValueError('Incomplete stopped memory read')
        if key in rows and rows[key] != value:
            raise DebuggerError('Stopped memory changed during observation')
        if key not in rows:
            total += length
            rows[key] = value
        return value

    def physical(a, n):
        return sample('physical', read_physical, a, n)

    def virtual(a, n):
        return sample('virtual', read_virtual, a, n)

    def linear(a, n):
        return translate_linear(context, a, n, physical, virtual)[0]

    try:
        result = _interpret(image, cpu, context, linear)
        address = cpu['cs_base'] + cpu['ip']
        data, walks = translate_linear(context, address, result['instruction_size'], physical, virtual)
        # Recheck every exact read, including page tables and descriptor material.
        for (space, address_, length), expected in list(rows.items()):
            reader = read_physical if space == 'physical' else read_virtual
            if reader(address_, length) != expected:
                raise DebuggerError('Stopped memory changed during observation')
        location = deepcopy(result['source_location'])
        obj = next(o for o in image.metadata['le']['objects'] if o['index'] == location['object_index'])
        region = next(r for r in image.regions if r.start == obj['virtual_address'])
        offset = location['object_offset']
        source = region.data[offset : offset + len(data)]
        qualification = dict(
            qualified=True,
            reason=None,
            instruction_size=len(data),
            execution_bytes=data.hex(),
            source_instruction_sha256=sha256(source).hexdigest(),
            source_location=location,
            context=dict(descriptor=deepcopy(result['descriptor'])),
        )
        mapping = dict(
            source_version=deepcopy(source_version),
            selector=cpu['cs'],
            linear_address=address,
            descriptor=deepcopy(result['descriptor']),
            instruction_backing=deepcopy(walks),
        )
        witness = [dict(space=s, address=a, length=n, hex=b.hex()) for (s, a, n), b in rows.items()]
        return dict(
            qualification=qualification,
            mapping_identity=mapping,
            witness=dict(cpu=deepcopy(cpu), context=deepcopy(context), reads=witness),
        )
    except DebuggerError:
        raise
    except (ValueError, KeyError, TypeError, StopIteration) as error:
        return _unknown(error)


def replay(image, source_version, witness):
    """Recompute an observation from retained exact stopped-read evidence."""
    try:
        rows = {}
        retained = witness['reads']
        if not isinstance(retained, list) or len(retained) > MAX_WITNESS_ROWS:
            raise ValueError('Replay witness row budget exceeded')
        total = 0
        for row in retained:
            n, encoded = row['length'], row['hex']
            if (
                type(n) is not int
                or n < 1
                or not isinstance(encoded, str)
                or len(encoded) != 2 * n
                or total + n > MAX_WITNESS_BYTES
            ):
                raise ValueError('Replay witness byte budget exceeded')
            total += n
            key = (row['space'], row['address'], row['length'])
            value = bytes.fromhex(row['hex'])
            if key in rows or len(value) != row['length']:
                raise ValueError('Malformed replay witness')
            rows[key] = value

        def reader(space):
            def read(a, n):
                try:
                    return rows[(space, a, n)]
                except KeyError:
                    raise ValueError('Missing replay read') from None

            return read

        return observe(
            image,
            source_version,
            witness['cpu'],
            witness['context'],
            reader('physical'),
            reader('virtual'),
        )
    except DebuggerError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        return _unknown(error)
