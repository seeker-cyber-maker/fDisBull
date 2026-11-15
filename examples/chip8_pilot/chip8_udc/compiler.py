"""Tool-first compiler: validated observed CHIP-8 word -> Python UDC module.

Reuses chip8lab decoder and pilot observation registry rather than interpreting
ROMs from scratch. The intermediate is explicitly a CANDIDATE, not common UIL.
Only exact observed PC/word pairs are specialized; unobserved, modified and
unimplemented sites defer to Machine.step().
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from chip8lab.decoder import decode_table
from chip8lab.pilot import instruction_candidate, run_rom
from chip8_udc.swedes import SWEDES, body_for
from chip8_udc.catalog import RuleCatalog

FORMAT = 'fdisbull-chip8-python-udc-study-1'
_NAME = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')


def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def observed_sites(rom: bytes, index_path: Path | None, *, steps=1600):
    """Consult existing UDL observation database first. No static word-as-code guess."""
    source_digest = sha(rom)
    if index_path is None:
        trace = run_rom(rom, steps=steps)
        if trace.get('trace_coverage_truncated'):
            raise ValueError('observation trace truncated: build larger index instead')
        rows = [(int(r['source_address'], 16), int(r['raw_word'], 16),
                 r['udl']['family'], r['observed_count'])
                for r in trace['block_candidates']]
        return rows, {'provenance': 'chip8lab.pilot.run_rom', 'observed_executions': trace['steps'],
                      'status': trace['status'], 'source_sha256': source_digest}
    db = sqlite3.connect('file:' + str(Path(index_path).resolve()) + '?mode=ro', uri=True)
    try:
        fmt = db.execute("SELECT value FROM metadata WHERE key='format'").fetchone()
        if fmt is None or fmt[0] != 'fdisbull-chip8-observation-study-1':
            raise ValueError('not a CHIP-8 pilot observation index')
        source_row = db.execute('SELECT platform FROM sources WHERE sha256=?', (source_digest,)).fetchone()
        if not source_row:
            raise ValueError('source SHA-256 not present in pilot observation registry')
        if source_row[0] != 'chip8':
            raise ValueError('profile mismatch: only classic chip8 source programs are admissible')
        rows = [(int(pc, 16), int(word, 16), family, count)
                for pc, word, family, count in db.execute('''
                SELECT pc,word,family,observed_count FROM block_candidates
                WHERE source_sha=? ORDER BY pc,word''', (source_digest,))]
        source_report = db.execute("SELECT value FROM metadata WHERE key='source_report_sha256'").fetchone()[0]
        return rows, {'provenance': 'chip8lab.registry.observations.sqlite',
                      'source_report_sha256': source_report, 'source_sha256': source_digest}
    finally:
        db.close()


def compile_rom(rom: bytes, *, module_name: str, index_path: Path | None = None,
                steps: int = 1600, catalog_path: Path | None = None) -> tuple[str, dict]:
    if not _NAME.fullmatch(module_name): raise ValueError('invalid module name')
    if not 0 < len(rom) <= 3584: raise ValueError('nonempty classic 4K ROM required')
    allowed=None; catalog_snapshot=None
    if catalog_path is not None:
        with RuleCatalog(catalog_path) as db:
            allowed=db.available()
            catalog_snapshot=db.summary()['catalog_sha256']
    records, provenance = observed_sites(rom, index_path, steps=steps)
    if not records: raise ValueError('no observed instruction sites: cannot specialize')
    chosen, remaining, all_candidates = [], [], []
    for pc, word, family, observed_count in records:
        offset = pc-0x200
        if offset < 0 or offset+1 >= len(rom):
            # Could be self-modified code or a trace beyond loaded ROM. Such
            # observations cannot be compiled from the input image directly.
            remaining.append({'pc': f'{pc:04X}', 'family': family,
                              'reason': 'outside_original_rom_image'});continue
        image_word = (rom[offset]<<8)|rom[offset+1]
        if image_word != word:
            remaining.append({'pc': f'{pc:04X}', 'family': family,
                              'reason': 'runtime_word_differs_from_source_image'});continue
        d=decode_table(word,'chip8')
        if d.family != family or d.tier != 'classic':
            raise ValueError(f'stale observation or unsupported profile at {pc:#x}: {word:04x}/{family}')
        candidate = instruction_candidate(pc, word)
        all_candidates.append({'pc':f'{pc:04X}', 'word':f'{word:04X}',
                               'intent':candidate['uil_intent_candidate'],
                               'family':family,'observed_count':observed_count,
                               'uil_status':'unqualified_candidate'})
        body=body_for(d,allowed)
        if body is None:
            remaining.append({'pc':f'{pc:04X}', 'family':family,
                              'word':f'{word:04X}', 'observed_count':observed_count,
                              'reason':'manual_swede_or_VM_fallback_required'})
        else:
            chosen.append((pc,word,family,body,observed_count))
    if not chosen: raise ValueError('no observed sites have an admitted Python rule')
    chosen.sort(key=lambda x:(x[0],x[1]))
    guards = []
    for pc,word,family,body,count in chosen:
        statements = '\n'.join('        '+line for line in body.splitlines())
        guards.append(
            f'    if pc == {pc} and fetched == {word}:\n'
            f'        m.last_family = {family!r}\n'
            f'        m.pc = pc + 2\n'
            f'{statements}\n'
            f'        m.steps += 1\n'
            f'        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1\n'
            f'        return "executed"')
    body = '\n'.join(guards)
    header = f'''"""Generated experimental Python UDC for a pinned CHIP-8 input.

NOT a canonical UIL compiler, and not proof of historical CHIP-8 equivalence.
The ROM is caller-supplied and SHA-256 checked; no program bytes are embedded.
Specialized paths are guarded by PC + fetched word; all other states use the
existing chip8lab.vm.Machine.step interpreter as a truthful fallback.
"""
from __future__ import annotations
import hashlib
from chip8lab.vm import Machine, Quirks, Trap

SOURCE_SHA256 = {sha(rom)!r}
FORMAT = {FORMAT!r}
MODULE_NAME = {module_name!r}
SPECIALIZED_SITES = {len(chosen)}

def create_machine(rom: bytes, *, seed: int=42, quirks=None):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256:
        raise ValueError('CHIP-8 ROM input does not match pinned source identity')
    m = Machine(seed=seed, quirks=quirks or Quirks())
    m.load_rom(rom)
    return m

def step(m: Machine, stats: dict | None=None):
    pc = m.pc
    if pc < 0 or pc + 1 >= 4096 or (m.waiting and not m.keys):
        if stats is not None: stats['fallback'] = stats.get('fallback', 0) + 1
        return m.step()
    fetched = (m.memory[pc] << 8) | m.memory[pc+1]
{body}
    if stats is not None: stats['fallback'] = stats.get('fallback', 0) + 1
    return m.step()
'''
    # No user-provided template/code is executed. Syntax-check generated source.
    compile(header, f'{module_name}.py', 'exec')
    counts = Counter(x[2] for x in chosen)
    manifest = {'format':FORMAT,'module_name':module_name,
                'source_sha256':sha(rom), 'source_bytes':len(rom),
                'source_provenance':provenance,
                'backend': 'Python 3.13 chip8lab Machine guarded partial evaluation',
                'intermediate':'fdisbull-chip8-udl-uil-candidate-1 (NOT canonical UIL)',
                'output':'generated Python using manually sweded pure/state opcode templates',
                'qualified_against':'bounded reference chip8lab.vm only',
                'distribution':'local-only until separate content review',
                'execution_authorized_by_registry':False,
                'manual_rules':sorted(SWEDES) if allowed is None else sorted(allowed),
                'rule_catalog_sha256':catalog_snapshot, 'sweded_families_observed':dict(sorted(counts.items())),
                'candidate_sites':all_candidates,
                'specialized_site_count':len(chosen),
                'observed_site_count':len(records),
                'fallback_sites':remaining,
                'fallback_family_count':dict(sorted(Counter(r['family'] for r in remaining).items())),
                'generated_source_sha256':sha(header.encode('utf-8')),
                'comment':'No original-game or real-hardware parity; no source-to-common-UIL proof.'}
    return header, manifest


def write_module(out:Path, source:str, manifest:dict):
    out=Path(out)
    if out.exists(): raise FileExistsError(out)
    if any((parent/'.git').is_file() or (parent/'.git'/'HEAD').is_file()
           for parent in (out.resolve(), *out.resolve().parents)):
        raise ValueError('generated Python outputs must stay outside a Git checkout')
    out.mkdir(parents=True)
    (out/(manifest['module_name']+'.py')).write_text(source, encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return out
