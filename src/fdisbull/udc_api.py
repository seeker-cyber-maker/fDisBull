"""Agent JSON surface for persistent snippet and implementation records."""
METHODS={
 'capture-snippet':'Capture immutable mapped/file spans; name,spans,[version,context,boundary,evidence,author]',
 'snippet-info':'Read a snippet; snippet,[full,include_bytes]',
 'snippets':'List snippet metadata; [version,limit,offset,full]',
 'link-snippets':'Link exact local/portable snippet endpoints; sources,targets,kind,domain,evidence,[assurance,adapters,unknowns,author,name]',
 'snippet-links':'List authored snippet relations; [limit,offset,full]',
 'snippet-link-info':'Read authored relation; link,[full]',
 'store-block-contract':'Register a typed block behavior; document,[author]',
 'block-contract-info':'Read immutable contract; contract,[full]',
 'block-contracts':'List contracts; [limit,offset,full]',
 'store-udl-layer':'Register a contract backing and adapter; document,[author]',
 'udl-layer-info':'Read immutable layer; layer,[full]',
 'udl-layers':'List layers; [limit,offset,full]',
 'select-udl-layers':'Pin logical bindings to exact layers; name,bindings,[program,target,author]',
 'udl-selection-info':'Read immutable selection; selection,[full]',
 'udl-selections':'List selections; [limit,offset,full]',
 'run-module-uil':'Execute a typed symbolic UIL composition; program,selection,[state,max_steps]',
 'run-udl-layer':'Explicitly execute and compare a bounded backing; layer,inputs,[caller_registers,max_steps]',
 'run-udl-selection':'Execute one selected logical binding; selection,binding,inputs,[caller_registers,max_steps]',
 'build-udc-shell':'Emit native PE64/ELF64/Mach-O arm64 from selected modules; selection,plan,destination,[target,service_adapters,capture_state,c_compiler]',
 'build-macos-block-probe':'Emit guarded ARM64 stdin/stdout analysis scaffold for one fixed UIL invoke; selection,destination,[c_compiler]; build only',
 'compile-udc-splice':'Emit source-bound binary substitutions; selection,recipe,destination,[output_name]',
}


def invoke(project,method,params):
 from . import udc_layers
 if method=='build-macos-block-probe':
  from .udc_macos_probe import build_macos_block_probe
  return build_macos_block_probe(project,**params)
 if method=='run-module-uil':
  from .udc_blueprint import execute_module_uil
  return execute_module_uil(project,**params)
 functions={
  'capture-snippet':project.capture_snippet,'snippet-info':project.snippet_info,'snippets':project.snippets,
  'link-snippets':project.link_snippets,'snippet-links':project.snippet_links,'snippet-link-info':project.snippet_link_info,
  'block-contract-info':project.contract_info,'block-contracts':project.contracts,
  'udl-layer-info':project.udl_layer_info,'udl-layers':project.udl_layers,
  'udl-selection-info':project.udl_selection_info,'udl-selections':project.udl_selections,
 }
 if method in functions:return functions[method](**params)
 functions={'store-block-contract':udc_layers.register_contract,'store-udl-layer':udc_layers.register_layer,
  'select-udl-layers':udc_layers.select_layers,'run-udl-layer':udc_layers.run_layer,
  'run-udl-selection':udc_layers.run_selection,'build-udc-shell':udc_layers.build_selection_shell,
  'compile-udc-splice':udc_layers.compile_splice_selection}
 if method not in functions:raise ValueError('unknown block method')
 return functions[method](project,**params)
