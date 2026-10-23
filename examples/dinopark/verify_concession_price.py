#!/usr/bin/env python3
"""Exercise delivered 0.11.0 on user-owned DinoPark; trace the gift-stand price.

--output must be a new directory outside Git. Its private/ directory retains
the copied game and byte-retaining project/native checkpoints. Only evidence/
is suitable for sharing. No game or checkpoint bytes accompany this source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    result = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Game inputs must not contain symbolic links')
        if path.is_file():
            result.append({'path':path.relative_to(directory).as_posix(),
                           'sha256':digest(path),'size':path.stat().st_size})
    return result


def route_step(x,y,name,guest_ms=1200,hold_ms=500):
    return [{'op':'click-frame','x':x,'y':y,'name':name+'.png',
             'grid_step':8,'hold_ms':hold_ms},
            {'op':'run','guest_ms':guest_ms,'timeout_ms':5000}]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery',required=True,type=Path)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    delivery=args.delivery.resolve(strict=True); game=args.game_dir.resolve(strict=True)
    output=args.output.resolve()
    if output==game or game in output.parents or output in game.parents:
        raise ValueError('Output must be separate from game inputs')
    if any((parent/'.git').exists() for parent in [output,*output.parents]):
        raise ValueError('Private game/database/state output must be outside Git')
    wheel=delivery/'packages/fdisbull-0.11.0-py3-none-any.whl'
    backend=delivery/'backend/native-macos-arm64/dosbox-x'
    assert digest(wheel)=='c8c877392e7f804cb9f14e344de2e55667cc928db5998f79c6b101f747a9e47b'
    assert digest(backend)=='0876e686d6a85f8c1b790db03314b81f471f5a5791dcad4929b90b63a1ebeced'
    sys.path.insert(0,str(wheel))
    import fdisbull
    from fdisbull.project import Project
    assert '.whl/' in fdisbull.__file__ and fdisbull.__version__=='0.11.0'
    assert digest(game/'DINOPARK.EXE')=='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
    assert digest(game/'DINOSG.001')=='bf7af4fa7b57c96ff67dcd545d4b6873aee70681c0a197844fd73a84c40d32c5'
    original=inventory(game)
    output.mkdir(parents=True,exist_ok=False)
    private=output/'private'; private.mkdir()
    evidence=output/'evidence'; evidence.mkdir()
    (output/'.gitignore').write_text('/private/\n')
    mounted=private/'game'; shutil.copytree(game,mounted)
    log=(evidence/'actions.jsonl').open('x',buffering=1)
    report={'result':'running','version':fdisbull.__version__,'module':fdisbull.__file__,
            'wheel_sha256':digest(wheel),'backend_sha256':digest(backend),
            'executable_sha256':digest(game/'DINOPARK.EXE'),'runs':[]}
    processes=[]
    def record(label,result):
        log.write(json.dumps({'label':label,'result':result})+'\n')
        return result
    def number(d,address,length=4):
        return int.from_bytes(bytes.fromhex(d.memory(address,length=length)['hex']),'little')
    def save_route(p,name,steps):
        route={'format':'fdisbull-script-1','steps':steps}
        (evidence/name).write_text(json.dumps(route,indent=2)+'\n')
        return p.debug_save_script(name,route)['script_id']
    def run_route(d,name,identifier):
        result=record(name,d.script(script_id=identifier,timeout_ms=60000))
        assert result['ok'],result.get('error')
        return result
    def start(p):
        d=p.debugger(backend,mounted);processes.append(d.rpc.process)
        report['runs'].append(d.run_id)
        assert d.rpc.capabilities.get('code_layers')
        return d
    def remove(d,watch):
        for bp in watch['breakpoints']:d.delete_breakpoint(bp['breakpoint_id'])
    def trace(p,d,name,count):
        artifact=d.trace(name,count=count,timeout_ms=5000)
        assert artifact['metadata']['complete']
        p.debug_export(artifact['artifact'],evidence/name)
        data=json.loads((evidence/name).read_text())
        record(name,artifact)
        return data
    def observed_ax(data):
        return int(data['events'][1]['register_changes']['eax'],16)&0xffff
    database=private/'dinopark.fdb'
    with Project.create(database,mounted/'DINOPARK.EXE',load_segment=0x1000) as p:
        boot=[{'op':'run','guest_ms':35000,'fast_forward':True,'timeout_ms':10000}]
        boot+=route_step(160,160,'01-old-game',1500,hold_ms=150)
        boot+=route_step(90,70,'02-select-pmm',300,hold_ms=150)
        boot+=route_step(250,73,'03-load-pmm',3000,hold_ms=150)
        boot+=[{'op':'screenshot','name':'04-pmm-street.png','grid':True,'grid_step':8}]
        boot_id=save_route(p,'boot-load-pmm.json',boot)
        store=[{'op':'run','guest_ms':120,'timeout_ms':3000}]
        for x,y,name,ms in [(260,120,'05-general-store',1200),(265,145,'06-enter-store',1600),
                             (205,105,'07-catalog',1000),(263,165,'08-cover',500),
                             (195,54,'09-concessions-tab',1500)]:
            store+=route_step(x,y,name,ms)
        store+=[{'op':'screenshot','name':'11-concessions-grid8.png','grid':True,'grid_step':8}]
        store_id=save_route(p,'street-to-concessions.json',store)
        with start(p) as d:
            entry_table=record('entry_price_table',d.memory('0x46a75',length=8))
            assert entry_table['hex']=='8813e8034c1d1027'
            watch=d.breakpoint('0x46a75',access='w',length=8)
            run_route(d,'boot',boot_id)
            remove(d,watch)
            street=record('street_checkpoint',d.save_state('pmm-street.sav'))
        with start(p) as d:
            record('restore_street_in_fresh_emulator',d.load_state(street['artifact']))
            watch=d.breakpoint('0x46a75',access='w',length=8)
            routed=run_route(d,'store',store_id)
            remove(d,watch)
            report['price_table_no_cpu_writes_during_boot_and_navigation']=True
            assert d.memory('0x46a75',length=8)['hex']==entry_table['hex']
            concessions=record('concessions_checkpoint',d.save_state('concessions.sav'))
            watch=d.breakpoint('0x46a79',access='r',length=2)
            d.click_frame(195,85,name='12-gift-price-watch-grid8.png',grid_step=8,hold_ms=500)
            hit=record('selection_read_watch',d.run(timeout_ms=5000))
            assert hit['outcome']=='breakpoint'
            access=hit['session']['stop_reason']['data_access']
            assert access['project_instruction']=='0x3414e'
            assert int(d.registers()['general']['eax'],16)&0xffff==7500
            remove(d,watch)
            # Menu time can leave this save unable to afford a $7,500 gift stand.
            # Preserve the original checkpoint and make a declared, guarded fork
            # of only actual/available cash for the two purchase comparisons.
            d.load_state(concessions['artifact'])
            cash_edits=[{'address':address,'expected_hex':d.memory(address,length=4)['hex'],
                         'data_hex':struct.pack('<I',100000).hex()}
                        for address in ('0x45e3a','0x4bcd4')]
            funded=record('controlled_affordability_fixture',p.debug_fork_state(
                concessions['artifact'],backend,mounted,name='funded-purchase-fixture.sav',
                memory=cash_edits))
            report['purchase_fixture']={'parent':concessions['artifact'],'fork':funded['artifact'],
                'edits':cash_edits,'cash':100000,'price_table_edited':False,
                'purpose':'Keep both bounded purchase trials affordable despite live calendar costs'}
            record('selection_seed',p.analyze(start='334b:0c9e',max_instructions=1))
            record('commit_seed',p.analyze(start='334b:0a95',max_instructions=1))
            d.load_state(concessions['artifact']);d.run(guest_ms=120,timeout_ms=3000)
            bp=d.breakpoint('334b:0c9e')
            d.click_frame(195,85,name='13-lookup-break-grid8.png',grid_step=8,hold_ms=500)
            assert d.run(timeout_ms=5000)['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id'])
            lookup=record('lookup_checkpoint',d.save_state('before-price-lookup.sav'))
            base=trace(p,d,'14-baseline-lookup.json',8);assert observed_ax(base)==7500
            d.load_state(lookup['artifact'])
            layer=p.debug_layer('Gift theory: food entry for selection, cash staging and commit',kind='execute',
                patches=[{'address':address,'expected_hex':'8b877568','data_hex':'8b877168'}
                         for address in ('334b:0c9e','334b:0dcf','334b:0a95')])
            report['layer']=layer;layer_id=layer['layer']
            record('enable_layer',d.layer_enable(layer_id,enabled=True))
            assert d.code('334b:0c9e',length=4,view='ram')['hex']=='8b877568'
            assert d.code('334b:0c9e',length=4)['hex']=='8b877168'
            alternate=trace(p,d,'15-layer-enabled-lookup.json',8);assert observed_ax(alternate)==5000
            d.load_state(lookup['artifact'])
            d.layer_enable(layer_id,enabled=True)
            record('disable_layer',d.layer_enable(layer_id,enabled=False))
            disabled=trace(p,d,'16-layer-disabled-lookup.json',8);assert observed_ax(disabled)==7500
            d.load_state(lookup['artifact']);d.layer_enable(layer_id,enabled=True)
            layered=record('layered_checkpoint',d.save_state('layer-enabled.sav'))
        with start(p) as d:
            record('restore_active_layer_in_fresh_emulator',d.load_state(layered['artifact']))
            assert d.layers()['active']==[layer_id]
            assert d.code('334b:0c9e',length=4)['hex']=='8b877168'
            restored=trace(p,d,'17-restored-layer-lookup.json',8);assert observed_ax(restored)==5000
            d.layers([])
            trials=[]
            for name,expected,active in [('baseline',7500,[]),('layered',5000,[layer_id])]:
                d.load_state(funded['artifact']);d.run(guest_ms=120,timeout_ms=3000)
                d.layers(active)
                steps=route_step(195,85,name+'-select-gift',1200)
                steps+=route_step(145,187,name+'-show-buy-button',1000)
                steps+=route_step(160,188,name+'-buy-one-gift',1500)
                identifier=save_route(p,name+'-order-gift.json',steps)
                run_route(d,name+'-order',identifier)
                assert d.memory('0x4bb14',length=8)['hex']=='0000000001000000'
                watch=d.breakpoint('0x46a79' if name=='baseline' else '0x46a75',access='r',length=2)
                d.click_frame(218,188,name=name+'-ok-grid8.png',grid_step=8,hold_ms=100)
                hit=record(name+'-commit-price-read',d.run(timeout_ms=5000))
                assert hit['outcome']=='breakpoint'
                assert hit['session']['stop_reason']['data_access']['project_instruction']=='0x33f45'
                assert int(d.registers()['general']['eax'],16)&0xffff==expected
                before={'cash':number(d,'0x45e3a'),'expenses':number(d,'0x45a5a'),
                        'available_cash':number(d,'0x4bcd4'),'ticks':d._timing()['guest_ticks']}
                remove(d,watch)
                commit=trace(p,d,name+'-commit-trace.json',192)
                after={'cash':number(d,'0x45e3a'),'expenses':number(d,'0x45a5a'),
                       'transaction_total':number(d,'0x46a6c'),'ticks':d._timing()['guest_ticks']}
                assert before['cash']-after['cash']==expected,(name,before,after)
                assert after['expenses']-before['expenses']==expected,(name,before,after)
                assert after['transaction_total']==expected
                assert before['ticks']==after['ticks']
                assert d.memory('0x471a6',length=8)['hex']=='0000000001000000'
                assert d.memory('0x46a75',length=8)['hex']==entry_table['hex']
                for address in ('334b:0c9e','334b:0dcf','334b:0a95'):
                    assert d.code(address,length=4,view='ram')['hex']=='8b877568'
                trials.append({'name':name,'charged':expected,'before':before,'after':after,
                               'gift_count':1,'trace_events':len(commit['events'])})
                d.layers([]);d.run(guest_ms=500,timeout_ms=3000)
                record(name+'-final-frame',d.screenshot(name+'-after-purchase.png',grid=True,grid_step=8))
            report.update(trials=trials,layer_lookup_values=[7500,5000,7500],
                          restored_layer_lookup=5000,code_ram_unchanged=True,price_table_unchanged=True,
                          compatible_state_restore_in_fresh_emulators=True)
        # Reopen the project only after all emulators have exited. Export stored frames.
    assert all(process.poll() is not None for process in processes)
    with Project(database) as p:
        for artifact in p.debug_artifacts()['artifacts']:
            if artifact['kind'] in ('screenshot','screenshot-grid','trace','code-snapshot'):
                path=evidence/artifact['name']
                if not path.exists():p.debug_export(artifact['id'],path)
        screen=next(a for a in p.debug_artifacts()['artifacts'] if a['name']=='11-concessions-grid8.png')
        regenerated=p.debug_grid(screen['metadata']['coordinate_grid']['source_artifact'],
                                name='offline-concessions-grid8.png',step=8,target=[195,85])
        p.debug_export(regenerated['artifact'],evidence/'offline-concessions-grid8.png')
        report['offline_grid_after_restart']={'width':regenerated['metadata']['width'],
            'height':regenerated['metadata']['height'],'step':8,'label_step':32}
    assert inventory(game)==original and inventory(mounted)==original
    report.update(result='pass',game_files_unchanged=len(original),processes_reaped=len(processes),
        private_database=str(database),private_checkpoints_exported=False,
        price_source={'file_offset':'0x3b279','project_address':'0x46a79',
                      'static_segmented':'4020:6879','word_hex':'4c1d','value':7500,
                      'selection_instruction':'334b:0c9e','cash_staging_instruction':'334b:0dcf',
                      'commit_instruction':'334b:0a95'})
    (evidence/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    (evidence/'original-inputs.json').write_text(json.dumps(original,indent=2)+'\n')
    log.close()
    print(json.dumps({'result':'pass','output':str(output),'trials':report['trials'],
                      'lookup_toggle':report['layer_lookup_values'],'game_files_unchanged':len(original)}))


if __name__=='__main__':main()
