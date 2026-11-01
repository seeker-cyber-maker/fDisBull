#!/usr/bin/env python3
"""Verify an original NEW GAME route with delivered fDisBull 0.16.0.

The preparation uses checked purchases, followed by bounded operating and
pixel-scene checks. It is a finite route, not a deterministic game solver.
All input files and databases remain private.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

sys.dont_write_bytecode = True
EXE_SHA = '2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
NAME = 'NewProfit16'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def entries(data):
    assert len(data) == 250
    return [dict(rank=i+1, name=data[i*25:i*25+21].split(b'\0')[0].decode('ascii'),
                 value=int.from_bytes(data[i*25+21:i*25+25], 'little', signed=True))
            for i in range(10)]


def main(args):
    delivery, original = args.delivery.resolve(), args.game_dir.resolve()
    work, evidence = args.work_dir.resolve(), args.evidence_dir.resolve()
    for target in [work, evidence]:
        if target == original or target in original.parents or original in target.parents:
            raise ValueError('Outputs must be separate from original game input')
        if any((p/'.git').exists() for p in [target, *target.parents]):
            raise ValueError('Game, states, database and new run outputs must remain outside Git')
    assert work != evidence and work not in evidence.parents and evidence not in work.parents
    before = inventory(original)
    assert before['DINOPARK.EXE'] == EXE_SHA
    assert NAME not in [x['name'] for x in entries((original/'TOPTEN.DAT').read_bytes())]
    work.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    game = work/'game'
    shutil.copytree(original, game, ignore=lambda _p, names: [n for n in names if n.upper().startswith('DINOSG.')])
    copied = inventory(game)
    assert not list(game.glob('DINOSG.*'))
    sys.path.insert(0, str(delivery))
    import fdisbull_delivery
    module = fdisbull_delivery.activate()
    from fdisbull.project import Project
    assert module.__version__ == '0.16.0'
    assert delivery in Path(module.__file__).resolve().parents
    journal = json.loads(args.journal.read_text())
    patterns = json.loads(args.patterns.read_text())
    assert journal['format'] == 'fdisbull-dinopark-recorded-newgame-1'
    receipt = dict(version=module.__version__, python=sys.version, module=module.__file__,
                   script_sha256=sha(Path(__file__).read_bytes()), journal_sha256=sha(args.journal.read_bytes()),
                   game_exe_sha256=EXE_SHA, saved_games_copied=0, native_state_restore_calls=0,
                   native_state_save_calls=0, memory_write_calls=0, register_write_calls=0,
                   code_layers=[], sessions=[])

    def save(name, value):
        (evidence/(name+'.json')).write_text(json.dumps(value, indent=2)+'\n')

    def shot(p, d, name):
        raw = d.screenshot(name+'.png')
        p.debug_export(raw['artifact'], evidence/(name+'.png'))
        grid = p.debug_grid(raw['artifact'], name=name+'-grid8.png', step=8)
        p.debug_export(grid['artifact'], evidence/(name+'-grid8.png'))
        return dict(clean=raw, grid=grid)

    def route(p, d, name, steps):
        script = dict(format='fdisbull-script-1', steps=steps)
        save(name+'.script', script)
        saved = p.debug_save_script(name, script)
        result = d.script(script_id=saved['script_id'], timeout_ms=120000)
        save(name+'.result', result)
        for item in result['steps']:
            if item['op'] == 'click-frame' and item['ok']:
                p.debug_export(item['result']['frame']['artifact'], evidence/(name+'-target-'+str(item['index'])+'.png'))
        assert result['ok'], result.get('error')
        return result

    def economy(d):
        result = {}
        for key, address, length in [('cash', '4020:5c3a', 4), ('loan', '4020:bfbb', 4), ('day', '4020:6fcb', 2)]:
            value = d.memory(address, length=length)
            result[key] = int.from_bytes(bytes.fromhex(value['hex']), 'little', signed=True)
        return result

    def trace(p, d, name, options):
        result = d.trace(name+'.trace.json', **options)
        p.debug_export(result['artifact'], evidence/(name+'.trace.json'))
        return result

    # A small task-local demonstration of deterministic scene checks. 0.16.0
    # still transports a PNG here; a future native pixel-probe API can avoid it.
    def probe(p, d):
        from PIL import Image
        frame = d.screenshot('scene-probe.png')
        with tempfile.TemporaryDirectory(dir=work) as directory:
            path=Path(directory)/'probe.png'
            p.debug_export(frame['artifact'], path)
            with Image.open(path) as source:
                rgb = source.convert('RGB')
                assert rgb.size == (320, 200)
                scores = {}
                for name, pattern in patterns['scenes'].items():
                    scores[name] = sum(all(abs(a-b) <= pattern['tolerance']
                        for a,b in zip(rgb.getpixel((s['x'],s['y'])),s['rgb']))
                        for s in pattern['samples'])
        return dict(frame_id=frame['metadata']['frame_id'], scores=scores,
                    matched=[n for n,s in scores.items() if s >= patterns['scenes'][n]['min_matches']])

    def wait_scene(p, d, name, label, guest_budget=8000):
        deadline = time.monotonic()+15
        progress = 0
        polls = []
        while True:
            observed = probe(p, d)
            polls.append(observed)
            if name in observed['matched']:
                save(label+'-scene-polls', dict(polls=polls,guest_elapsed_ms=progress,ok=True))
                return
            if progress >= guest_budget or time.monotonic() >= deadline:
                save(label+'-scene-polls', dict(polls=polls,guest_elapsed_ms=progress,ok=False))
                save(label+'-desync', shot(p,d,label+'-desync'))
                raise AssertionError(('Scene mismatch',name,observed))
            result = d.run(guest_ms=500,timeout_ms=3000,fast_forward=True)
            assert result['outcome']=='guest_time',result
            progress += result['guest_elapsed_ms']

    def named_click(p, d, control):
        target = patterns['controls'][control]
        wait_scene(p,d,target['scene'],control+'-before-click')
        route(p,d,control,[dict(op='click-frame',x=target['x'],y=target['y'],
              grid_step=8,name=control+'.png',hold_ms=80),
              dict(op='run',guest_ms=1800,timeout_ms=3000,fast_forward=True)])

    def settle_and_record(p, d):
        progress=0;polls=[];deadline=time.monotonic()+60
        while progress <= 150000 and time.monotonic() < deadline:
            observed=probe(p,d)
            values=economy(d)
            month=int.from_bytes(bytes.fromhex(d.memory('4020:ccfe',length=2)['hex']),'little')
            polls.append(dict(**observed,economy=values,month=month))
            handler=next((h for h in patterns['popup_handlers'] if h['when'] in observed['matched']),None)
            if handler:
                handled=route(p,d,'ack-'+handler['when'],[dict(op='keyboard.press',key=handler['key']),
                      dict(op='run',guest_ms=600,timeout_ms=3000,fast_forward=True)])
                progress+=sum(x['result'].get('guest_elapsed_ms',0) for x in handled['steps'] if x['ok'] and x['op']=='run')
                continue
            if 'street' not in observed['matched']:
                save('solvency-wait',dict(ok=False,polls=polls,guest_elapsed_ms=progress))
                save('solvency-desync',shot(p,d,'solvency-desync'))
                raise AssertionError(('Unexpected scene while waiting',observed))
            if month>=3 and values['cash']>values['loan']+750:
                break
            result=d.run(guest_ms=1000,timeout_ms=3000,fast_forward=True)
            assert result['outcome']=='guest_time',result
            progress+=result['guest_elapsed_ms']
        else:
            save('solvency-timeout',shot(p,d,'solvency-timeout'))
            raise AssertionError('Solvency wait exhausted its guest or wall budget')
        save('solvency-wait',dict(ok=True,polls=polls,guest_elapsed_ms=progress))
        named_click(p,d,'street.office');wait_scene(p,d,'office','office-ready')
        named_click(p,d,'office.profits')
        d.run(guest_ms=1200,timeout_ms=3000,fast_forward=True)
        save('completed-month-profit',shot(p,d,'completed-month-profit'))
        route(p,d,'ack-profit-report',[dict(op='keyboard.press',key='enter'),
              dict(op='run',guest_ms=1500,timeout_ms=3000,fast_forward=True)])
        named_click(p,d,'office.bank');wait_scene(p,d,'bank','bank-ready')
        named_click(p,d,'bank.payoff');wait_scene(p,d,'paid_popup','payoff-confirmation')
        route(p,d,'ack-payoff',[dict(op='keyboard.press',key='enter'),
              dict(op='run',guest_ms=700,timeout_ms=3000,fast_forward=True)])
        wait_scene(p,d,'bank','bank-committed')
        values=economy(d)
        assert values['loan']==0 and values['cash']>500,values
        receipt['debt_free_before_sale']=values
        save('debt-free-bank',shot(p,d,'debt-free-bank'))
        named_click(p,d,'bank.ok');wait_scene(p,d,'office','office-before-sale')
        save('writer-analysis',p.analyze(start='0x281c9',cs='0x27e5',max_instructions=16))
        bp=d.breakpoint('27e5:0379');save('writer-breakpoint',bp);assert bp['bytes_verified']
        named_click(p,d,'office.sell');wait_scene(p,d,'confirm_sale','sale-confirmation')
        route(p,d,'confirm-sale',[dict(op='click-frame',x=176,y=110,grid_step=8,name='confirm-sale.png'),
              dict(op='run',guest_ms=3000,timeout_ms=5000,fast_forward=True)])
        wait_scene(p,d,'name_prompt','name-prompt-ready')
        route(p,d,'type-earned-name',[dict(op='keyboard.type',text=NAME),
              dict(op='run',guest_ms=1600,timeout_ms=5000,fast_forward=True),
              dict(op='keyboard.press',key='o',modifiers=['ctrl']),
              dict(op='run',guest_ms=300,timeout_ms=5000,fast_forward=True)])
        assert bytes.fromhex(d.memory('4020:cce3',length=21)['hex']).split(b'\0')[0]==NAME.encode()
        save('typed-earned-name',shot(p,d,'typed-earned-name'))
        route(p,d,'confirm-earned-name',[dict(op='click-frame',x=160,y=126,grid_step=8,name='ok.png'),
              dict(op='run',timeout_ms=5000,fast_forward=True,expect='breakpoint')])
        assert d.registers()['project_address']=='0x281c9'
        save('writer-entry',trace(p,d,'writer-entry',dict(count=128,timeout_ms=10000)))
        d.delete_breakpoint(bp['breakpoint_id'])
        d.run(guest_ms=6000,timeout_ms=10000,fast_forward=True)
        save('earned-leaderboard',shot(p,d,'earned-leaderboard'))

    options = fdisbull_delivery.dos_options()
    with Project.create(work/'writer.fdb', game/'DINOPARK.EXE', load_segment=0x1000) as p:
        with p.debugger(game_dir=game, **options) as d:
            first = dict(run=d.run_id, pid=d.rpc.process.pid, backend_sha256=d.metadata['emulator_sha256'])
            for item in journal['commands']:
                cmd = dict(item['command'])
                op = cmd.pop('op')
                name = cmd.pop('name', op)
                label = f"recorded-{item['phase']:03d}-{name}"
                if op == 'script':
                    result = route(p, d, label, cmd['steps'])
                elif op == 'screenshot':
                    result = shot(p, d, label)
                elif op == 'analyze':
                    result = p.analyze(start=cmd.pop('address'), **cmd)
                elif op == 'economy':
                    result = economy(d)
                    if 'expected_cash' in item:
                        assert result['cash'] == item['expected_cash'], (label, result)
                    if item['phase'] == 186:
                        assert result['loan'] == 0 and result['cash'] > 500, result
                        receipt['debt_free_before_sale'] = result
                elif op == 'trace':
                    result = trace(p, d, label, cmd)
                elif op == 'table':
                    data = (game/'TOPTEN.DAT').read_bytes()
                    result = dict(sha256=sha(data), entries=entries(data))
                else:
                    assert op in ('run', 'click', 'click_frame', 'keyboard_press', 'keyboard_type',
                                  'keyboard_state', 'registers', 'memory', 'breakpoint',
                                  'delete_breakpoint', 'code', 'status'), op
                    result = getattr(d, op)(**cmd)
                    if 'expected_hex' in item:
                        assert result['hex'] == item['expected_hex'], (label,result)
                save(label, result)
            settle_and_record(p,d)
            after = (game/'TOPTEN.DAT').read_bytes()
            found = [x for x in entries(after) if x['name'] == NAME]
            assert len(found) == 1 and found[0]['value'] > 500, found
            assert receipt['debt_free_before_sale']['loan'] == 0
            receipt['entry'] = found[0]
            receipt['after_topten_sha256'] = sha(after)
        assert d.rpc.process.poll() is not None
        first['process_reaped'] = True
        receipt['sessions'].append(first)
    print(json.dumps(dict(writer_complete=True, entry=receipt['entry'])), flush=True)

    def advance(ms):
        return dict(op='run', guest_ms=ms, timeout_ms=15000, fast_forward=True, expect='guest_time')

    def click(x, y, name):
        return dict(op='click-frame', x=x, y=y, name=name+'.png', grid_step=8, hold_ms=80)

    # A second NEW GAME has no imported saved park. Even this park's zero sale
    # value goes through the real table reader before qualification is checked.
    with Project.create(work/'reader.fdb', game/'DINOPARK.EXE', load_segment=0x1000) as p:
        with p.debugger(game_dir=game, **options) as d:
            second = dict(run=d.run_id, pid=d.rpc.process.pid, backend_sha256=d.metadata['emulator_sha256'])
            assert second['run'] != first['run'] and second['pid'] != first['pid']
            route(p, d, 'fresh-new-game', [advance(35000), click(80,160,'new-game'), advance(2500),
                  click(160,132,'loan-ack'), advance(5000), click(175,140,'office'), advance(2500)])
            for linear, offset, name in [(0x28228,'03d8','entry'), (0x28377,'0527','return')]:
                save('reader-'+name+'-analysis', p.analyze(start=hex(linear), cs='0x27e5', max_instructions=16))
                bp = d.breakpoint('27e5:'+offset)
                save('reader-'+name+'-breakpoint', bp)
                assert bp['bytes_verified']
                if name == 'entry':
                    entry_bp = bp['breakpoint_id']
                else:
                    return_bp = bp['breakpoint_id']
            route(p, d, 'fresh-read', [click(252,151,'sell'), advance(1000), click(176,110,'confirm'),
                  dict(op='run',timeout_ms=5000,fast_forward=True,expect='breakpoint')])
            assert d.registers()['project_address'] == '0x28228'
            result = trace(p, d, 'fresh-reader', dict(count=128, timeout_ms=10000))
            assert result['metadata']['complete']
            d.delete_breakpoint(entry_bp)
            save('reader-return-stop', d.run(timeout_ms=5000, fast_forward=True))
            regs = d.registers()
            assert regs['project_address'] == '0x28377'
            save('reader-return-registers', regs)
            address = int(regs['segments']['ss'],16)*16 + ((int(regs['general']['ebp'],16)-0xfa)&0xffff)
            raw = d.call('memory.read', dict(address=dict(space='linear',offset=f'0x{address:08X}'),length=250))
            data = base64.b64decode(raw['data_base64'], validate=True)
            assert data == after
            receipt['fresh_guest_readback'] = dict(byte_count=250, sha256=sha(data),
                full_table_equal_to_written_disk=True, entry=receipt['entry'], runtime_address=hex(address))
            d.delete_breakpoint(return_bp)
            d.run(guest_ms=1500, timeout_ms=10000, fast_forward=True)
            save('fresh-after-read', shot(p, d, 'fresh-after-read'))
        assert d.rpc.process.poll() is not None
        second['process_reaped'] = True
        receipt['sessions'].append(second)
    assert inventory(original) == before
    current = inventory(game)
    assert set(current) == set(copied)
    receipt['private_changed_files'] = [k for k in current if current[k] != copied[k]]
    assert receipt['private_changed_files'] == ['TOPTEN.DAT']
    assert (game/'TOPTEN.DAT').read_bytes() == after
    receipt.update(original_files_unchanged=len(before), ok=True)
    save('VERIFICATION', receipt)
    save('SHA256SUMS', inventory(evidence))
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['delivery', 'game-dir', 'work-dir', 'evidence-dir']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--journal', type=Path, default=Path(__file__).with_name('routes')/'newgame-profit.json')
    parser.add_argument('--patterns', type=Path, default=Path(__file__).with_name('routes')/'newgame-pixel-patterns.json')
    main(parser.parse_args())
