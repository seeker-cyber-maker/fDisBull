"""Coordinate aids retain the real frame and use unchanged click pixels."""
import hashlib
import io

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.project import Project
from test_dos_loader import mz_file
from test_debugger import emulator


def test_real_grid_route_click_and_offline_regeneration(tmp_path,emulator):
    module=bytes.fromhex('b81300cd10ebfe')+bytes(505)
    binary=tmp_path/'GRID.EXE';binary.write_bytes(mz_file(module,ss=0,sp=0x200))
    path=tmp_path/'grid.fdb'
    with Project.create(path,binary) as p,p.debugger(emulator,tmp_path) as d:
        assert d.run(guest_ms=100,timeout_ms=2000,fast_forward=True)['outcome']=='guest_time'
        result=d.script({'format':'fdisbull-script-1','steps':[
            {'op':'screenshot','name':'menu-grid.png','grid':True,'grid_step':40,'as':'frame'},
            {'op':'click','x':279,'y':159,'mode_id':'$frame.metadata.mode_id'},
        ]})
        assert result['ok'],result
        gridded=next(a for a in p.debug_artifacts()['artifacts'] if a['kind']=='screenshot-grid')
        overlay=gridded['metadata']['coordinate_grid']
        source=overlay['source_artifact']
        clean=next(a for a in p.debug_artifacts()['artifacts'] if a['id']==source)
        assert (gridded['metadata']['width'],gridded['metadata']['height'])==(320,200)
        assert clean['kind']=='screenshot' and overlay['step']==40
        assert overlay['coordinate_space']=='screenshot_pixels' and overlay['origin']==[0,0]
        assert overlay['max_coordinate']==[319,199]
        assert overlay['source_sha256']==clean['sha256']
        assert gridded['metadata']['sha256']==gridded['sha256']!=clean['sha256']
        mode=clean['metadata']['mode_id']
        count=len(p.debug_artifacts()['artifacts'])
        for options in ({'grid':1},{'grid':True,'grid_step':True},{'grid':True,'grid_step':0}):
            with pytest.raises(ValueError):d.screenshot(**options)
        assert len(p.debug_artifacts()['artifacts'])==count
    assert d.rpc.process.poll() is not None
    # No emulator is needed to render another grid after both owners close.
    response=respond({'method':'debug-grid','params':{'project':str(path),'artifact':source,'step':32}})
    assert response['ok'],response
    regenerated=response['result']
    with Project(path) as p:
        assert len(p.debug_runs()['runs'])==1
        assert regenerated['metadata']['mode_id']==mode
        raw=tmp_path/'raw.png';grid=tmp_path/'grid.png'
        p.debug_export(source,raw);p.debug_export(regenerated['artifact'],grid)
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==clean['sha256']
        with Image.open(raw) as original,Image.open(grid) as annotated:
            assert original.size==annotated.size==(320,200)
            assert original.convert('RGB').getpixel((32,100))!=annotated.getpixel((32,100))[:3]
        assert next(a for a in p.debug_artifacts()['artifacts'] if a['id']==source)['sha256']==clean['sha256']
        with pytest.raises(ValueError,match='original screenshot'):
            p.debug_grid(regenerated['artifact'])


def test_grid_geometry_and_limits_are_explicit():
    from fdisbull.screenshot_grid import coordinate_grid
    image=Image.new('RGB',(320,200),(20,30,40));stream=io.BytesIO();image.save(stream,format='PNG')
    data,metadata=coordinate_grid(stream.getvalue(),step=32)
    assert metadata['x_lines']==list(range(0,320,32))
    assert metadata['y_lines']==list(range(0,200,32))
    with Image.open(io.BytesIO(data)) as rendered:
        assert rendered.size==(320,200) and rendered.getpixel((45,45))[:3]==(20,30,40)
    for step in (8,10):
        dense,geometry=coordinate_grid(stream.getvalue(),step=step,target=[160,160])
        assert geometry['x_lines']==list(range(0,320,step))
        assert geometry['label_step']>=32 and geometry['label_step']%step==0
        assert geometry['target']==[160,160]
        with Image.open(io.BytesIO(dense)) as rendered:
            assert rendered.size==(320,200) and rendered.getpixel((160,160))==(255,90,180)
    for value in (0,7,513,True,'32'):
        with pytest.raises(ValueError):coordinate_grid(stream.getvalue(),step=value)
    for target in ([320,0],[-1,10],[1,200],[True,10],[1],{'x':1,'y':2}):
        with pytest.raises(ValueError):coordinate_grid(stream.getvalue(),step=8,target=target)


def test_real_marked_click_is_one_script_action_with_fresh_frame(tmp_path,emulator):
    binary=tmp_path/'POINT.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('b81300cd10ebfe')+bytes(505),ss=0,sp=0x200))
    with Project.create(tmp_path/'point.fdb',binary) as p,p.debugger(emulator,tmp_path) as d:
        d.run(guest_ms=100,timeout_ms=2000,fast_forward=True)
        result=d.script({'format':'fdisbull-script-1','steps':[
            {'op':'click-frame','x':160,'y':160,'grid_step':8,'hold_ms':50,'as':'action'},
            {'op':'assert','value':'$action.frame.metadata.coordinate_grid.target','equals':[160,160]},
            {'op':'run','guest_ms':150,'timeout_ms':2000,'fast_forward':True},
        ]})
        assert result['ok'],result
        clicks=[e for e in p.debug_events(d.run_id)['events'] if e['operation']=='click']
        assert len(clicks)==1
        action=next(e['evidence'] for e in p.debug_events(d.run_id)['events'] if e['operation']=='click-frame')
        assert action['frame_phase']=='before_queued_click'
        assert action['mode_id']==action['frame']['metadata']['mode_id']
        assert action['frame']['metadata']['coordinate_grid']['step']==8
        assert action['frame']['metadata']['coordinate_grid']['label_step']==32
        with pytest.raises(ValueError,match='mode'):
            d.click_frame(160,160,mode_id=action['mode_id']+1)
        with pytest.raises(ValueError,match='outside'):
            d.click_frame(320,199)
        assert len([e for e in p.debug_events(d.run_id)['events'] if e['operation']=='click'])==1
    assert d.rpc.process.poll() is not None
