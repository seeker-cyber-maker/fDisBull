"""Small dependency checks, not fDisBull or native-debugger acceptance."""
from __future__ import annotations

import io
import json
import platform
import sys
from importlib import metadata, util
from pathlib import Path

import capstone
import iced_x86
import lief
import z3
from PIL import Image


def main() -> None:
    results = {}
    raw = bytes.fromhex('b80700050500')  # 16-bit MOV AX,7; ADD AX,5.
    instructions = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16).disasm(raw, 0x100))
    assert [(i.mnemonic, i.size) for i in instructions] == [('mov', 3), ('add', 3)]
    results['capstone'] = {'status': 'passed', 'check': 'Decode an authored x86-16 MOV/ADD fragment',
                           'instruction_count': len(instructions), 'python_version': capstone.__version__,
                           'native_version': list(capstone.cs_version())}

    decoded = list(iced_x86.Decoder(16, raw, ip=0x100))
    assert [i.mnemonic for i in decoded] == [iced_x86.Mnemonic.MOV, iced_x86.Mnemonic.ADD]
    assert [i.len for i in decoded] == [3, 3]
    results['iced-x86'] = {'status': 'passed', 'check': 'Decode the same authored x86-16 fragment',
                           'instruction_count': len(decoded)}

    native_file = Path('/bin/true').resolve()
    binary = lief.parse(str(native_file))
    assert binary is not None and isinstance(binary, lief.ELF.Binary)
    assert len(binary.sections) > 0
    results['lief'] = {'status': 'passed', 'check': 'Parse an existing host ELF without executing it',
                       'input': str(native_file), 'sections': len(binary.sections),
                       'machine_type': str(binary.header.machine_type), 'runtime_version': lief.__version__}

    pixels = [(0, 0, 0), (255, 255, 255), (10, 20, 30), (255, 0, 128)]
    image = Image.new('RGB', (2, 2)); image.putdata(pixels)
    buffer = io.BytesIO(); image.save(buffer, format='PNG'); buffer.seek(0)
    with Image.open(buffer) as restored:
        restored.load()
        assert restored.size == (2, 2) and restored.mode == 'RGB'
        assert restored.tobytes() == image.tobytes()
    results['pillow'] = {'status': 'passed', 'check': 'In-memory authored 2x2 PNG encode/decode round trip'}

    x, y = z3.BitVecs('x y', 8)
    equivalent = z3.Solver(); equivalent.set(timeout=5000)
    equivalent.add(x + y != y + x)
    assert equivalent.check() == z3.unsat
    mutant = z3.Solver(); mutant.set(timeout=5000)
    mutant.add(x + 1 != x)
    assert mutant.check() == z3.sat
    results['z3-solver'] = {'status': 'passed', 'check': '8-bit arithmetic equivalence and non-equivalence probes',
                            'equivalence': 'unsat', 'deliberate_difference': 'sat',
                            'version': z3.get_version_string()}

    package_versions = {p: metadata.version(p) for p in ['capstone', 'iced-x86', 'lief', 'pillow', 'z3-solver']}
    assert package_versions == {'capstone':'5.0.9','iced-x86':'1.21.0','lief':'1.0.0','pillow':'12.3.0','z3-solver':'5.3.2.0'}
    assert util.find_spec('fdisbull') is None and util.find_spec('fdisbull_player') is None
    report = {'purpose':'Dependency installation smoke checks only', 'python': platform.python_version(),
              'executable': sys.executable, 'packages': package_versions, 'checks': results,
              'fdisbull_present_in_this_venv': False, 'player_present_in_this_venv': False,
              'native_debugger_run': False, 'game_run': False}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
