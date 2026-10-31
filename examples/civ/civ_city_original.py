"""Original x86-16 observations, separate from authored UIL and its compiler.

Only the pinned private unpacked executable is accepted. The two original code
spans execute unchanged in the guarded CPU provider with explicit data/frame
adapters. This is not a DOS playthrough or whole-city execution.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from fdisbull.udc_native16 import execute_native16

PINNED = "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"


class OriginalCity:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != PINNED:
            raise ValueError("original oracle requires the pinned unpacked Civ executable")
        h = struct.unpack_from("<14H", raw)
        end = (h[2]-1)*512+h[1] if h[1] else h[2]*512
        self.module = raw[h[4]*16:end]
        self.spans = {"reset": (0xD244, 0xD26F), "accumulate": (0xE622, 0xE658)}

    def _execute(self, part, inputs, *, city=0, frame=0x9000):
        if type(city) is not int or not 0 <= city < 128:
            raise ValueError("city must be in 0..127")
        at = 0x70EC + 28*city
        adapter = {
            "segments": {"cs":"code","ds":"data","es":"data","ss":"frame"},
            "registers": {"bp":frame,"bx":28*city},
            "inputs": {"box":{"segment":"ds","offset":at+14}},
            "outputs": {"box":{"segment":"ds","offset":at+14}},
            "initializers":[{"segment":"ss","offset":frame+6,
                             "bytes_hex":city.to_bytes(2,"little").hex()}],
        }
        types = {"box":"i16"}
        if part == "accumulate":
            adapter["inputs"].update(gross={"segment":"ds","offset":0x70DC},
                maintenance={"segment":"ds","offset":0xD2F6},
                status={"segment":"ds","offset":at+6})
            adapter["scratch"]=[{"segment":"ss","offset":frame-0xE8,"size":2}]
            types.update(gross="i16",maintenance="i16",status="u8")
        begin, end = self.spans[part]
        result = execute_native16(self.module[begin:end], {"origin":begin-0xD120},
                                  adapter, inputs, types, {"box":"i16"}, max_steps=64)
        return result

    def observe(self, stock, delta, disorder, *, city=0, frame=0x9000, maintenance=0):
        """Reset original storage, then run the original contribution update."""
        if type(disorder) is not bool:
            raise ValueError("disorder needs a boolean")
        reset = self._execute("reset", {"box":stock}, city=city, frame=frame)
        gross = ((delta+maintenance+32768) % 65536)-32768
        update = self._execute("accumulate", {"box":reset["outputs"]["box"],
            "gross":gross,"maintenance":maintenance,"status":int(disorder)},city=city,frame=frame)
        return dict(original_sha256=PINNED, stock_before=stock, sanitized_stock=reset["outputs"]["box"],
                    delta=delta,disorder=disorder,result=update["outputs"]["box"],
                    reset=reset,update=update,
                    scope="two isolated original instruction spans; not a whole city/game")
