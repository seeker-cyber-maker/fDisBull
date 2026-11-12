"""Map declared AGI commands to typed object/resource effect ports."""
from .agi_effects import CONTRACT

SUPPORTED = {30,33,35,36,37,38,39,41,61,65,69,70,71,77,78,79,83,84,85,88,89,101}


def lower_effect(compiler,logic,pc,facts):
    op=facts['opcode'];a=compiler.resources[logic].code[pc+1:pc+facts['size']]
    if op not in SUPPORTED:raise ValueError('unsupported AGI effect')
    args,outputs={},{}
    actions={30:'resource.load_view',33:'object.animate',35:'object.draw',36:'object.erase',
             37:'object.position',38:'object.position',39:'object.get_position',41:'object.set_view',
             61:'object.ignore_horizon',65:'object.land_only',69:'object.distance',
             70:'object.stop_cycling',71:'object.start_cycling',77:'object.stop_motion',
             78:'object.start_motion',79:'object.step_size',83:'object.follow_ego',
             84:'object.wander',85:'object.normal_motion',88:'object.ignore_blocks',
             89:'object.observe_blocks',101:'ui.print'}
    if op==30:args={'view':a[0]}
    elif op==69:
        args={'first':a[0],'second':a[1]}
        outputs={'distance':compiler.variable(a[2],write=True)}
    elif op==101:
        args={'message':a[0],'output_mode':compiler.ref(15,flag=True),'window_timer':compiler.ref(21)}
        outputs={'output_mode':compiler.variable(15,flag=True,write=True),
                 'window_timer':compiler.variable(21,write=True)}
    else:
        args={'object':a[0]}
        if op==41:args['view']=a[1]
        elif op in (37,38):
            args.update(x=compiler.ref(a[1]) if op==38 else a[1],
                        y=compiler.ref(a[2]) if op==38 else a[2])
        elif op==39:
            outputs={'x':compiler.variable(a[1],write=True),'y':compiler.variable(a[2],write=True)}
        elif op==79:args['size']=compiler.ref(a[1])
        elif op==83:
            args['step']=a[1];outputs={'completion':compiler.variable(a[2],flag=True,write=True)}
        elif op in (77,78) and a[0]==0:
            outputs={'ego_direction':compiler.variable(6,write=True)}
    return compiler.node(logic,pc,facts,'effect',primary=False,suffix='_effect',
                         contract=CONTRACT,action=actions[op],args=args,outputs=outputs,
                         binding=compiler.resources[logic].resource_sha256)
