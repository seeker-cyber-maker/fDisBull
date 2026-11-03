"""Inventory source UI sites and bind the finite Z design to three revisions.

This surveys every C translation unit for the declared call vocabulary. A
source call and a reachable source ancestor are not a visited native screen.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
import subprocess

from fdisbull.strategy_z import screen_catalog


UI_CALLS = {'show_menu','menu_choose','menu_core','menu_dialog','show_msg','ad_wait',
            'key_cmd','getch','kbhit','show_help','news_box','news_effect','edit_line',
            'poll_mouse','load_screen','load_picture','city_process','city_scene'}


def nodes(node):
    yield node
    for child in node.children:
        yield from nodes(child)


def function_name(node, raw):
    item=node.child_by_field_name('declarator')
    while item is not None and item.type!='identifier':
        item=item.child_by_field_name('declarator')
    return raw[item.start_byte:item.end_byte].decode() if item is not None else None


def inventory(sources, output):
    from tree_sitter import Language, Parser
    import tree_sitter_c
    parser=Parser(Language(tree_sitter_c.language()))
    catalog=screen_catalog(); editions=[]
    for spec in sources:
        root=Path(spec['directory']).resolve()
        revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        files, functions, site_keys, sites, errors = [], {}, set(), [], []
        for path in sorted((root/'src').glob('*.C')):
            relative=path.relative_to(root).as_posix(); raw=path.read_bytes()
            if raw!=subprocess.check_output(['git','-C',str(root),'show',revision+':'+relative]):
                raise ValueError('UI source differs from pinned Git object')
            tree=parser.parse(raw)
            if tree.root_node.has_error: errors.append(relative)
            files.append(dict(path=relative,sha256=hashlib.sha256(raw).hexdigest()))
            for node in nodes(tree.root_node):
                if node.type!='function_definition': continue
                name=function_name(node,raw)
                if name is None: continue
                key=(relative,name)
                if key in functions:
                    raise ValueError('ambiguous source function identity')
                calls=[]
                for call in nodes(node):
                    if call.type!='call_expression': continue
                    target=call.child_by_field_name('function')
                    if target is None: continue
                    callee=raw[target.start_byte:target.end_byte].decode(errors='replace')
                    if target.type!='identifier':
                        callee='<indirect>'
                    calls.append(callee)
                    if callee in UI_CALLS:
                        site_key=(relative,call.start_byte)
                        site_keys.add(site_key)
                        sites.append(dict(path=relative,function=name,line=call.start_point.row+1,
                                          byte_offset=call.start_byte,callee=callee))
                functions[key]=dict(path=relative,name=name,start_line=node.start_point.row+1,
                    end_line=node.end_point.row+1,sha256=hashlib.sha256(raw[node.start_byte:node.end_byte]).hexdigest(),
                    calls=sorted(set(calls)))
            # K&R implicit-int definitions are not recognized by the modern C
            # grammar. Parse an explicit-return-type VIEW of the exact suffix;
            # retain original extents/hashes, and label this recovery. Sources
            # and the error-bearing original tree remain untouched.
            for match in re.finditer(rb'^([A-Za-z_]\w*)\([A-Za-z_, \t]*\)\s*\r?\n',raw,re.M):
                name=match[1].decode(); key=(relative,name)
                if key in functions: continue
                synthetic=b'int '+raw[match.start():]
                recovered=parser.parse(synthetic).root_node.named_children
                if not recovered or recovered[0].type!='function_definition': continue
                node=recovered[0]
                if function_name(node,synthetic)!=name: continue
                end=match.start()+node.end_byte-4
                calls=[]
                for call in nodes(node):
                    if call.type!='call_expression': continue
                    target=call.child_by_field_name('function')
                    if target is None: continue
                    callee=synthetic[target.start_byte:target.end_byte].decode(errors='replace') if target.type=='identifier' else '<indirect>'
                    calls.append(callee)
                    if callee in UI_CALLS:
                        pos=match.start()+call.start_byte-4
                        site_keys.add((relative,pos))
                        sites.append(dict(path=relative,function=name,line=raw[:pos].count(b'\n')+1,
                                          byte_offset=pos,callee=callee))
                functions[key]=dict(path=relative,name=name,start_line=raw[:match.start()].count(b'\n')+1,
                    end_line=raw[:end].count(b'\n')+1,sha256=hashlib.sha256(raw[match.start():end]).hexdigest(),
                    calls=sorted(set(calls)),parse_recovery='explicit-int parsing view of original implicit-int declaration')
            # Keep top-level/parser-gap sites rather than dropping them.
            for call in nodes(tree.root_node):
                if call.type!='call_expression': continue
                target=call.child_by_field_name('function')
                if target is None: continue
                callee=raw[target.start_byte:target.end_byte].decode(errors='replace')
                if callee in UI_CALLS and (relative,call.start_byte) not in site_keys:
                    sites.append(dict(path=relative,function=None,line=call.start_point.row+1,
                                      byte_offset=call.start_byte,callee=callee))
        anchors=[]; roots=defaultdict(set); missing=[]
        for family in catalog['families']:
            for anchor in family['source_anchors']:
                for symbol in anchor['symbols']:
                    key=(anchor['file'],symbol)
                    if key not in functions:
                        missing.append(dict(scene=family['id'],file=key[0],symbol=symbol))
                    else:
                        roots[key].add(family['id'])
                        anchors.append(dict(scene=family['id'],**{k:v for k,v in functions[key].items() if k!='calls'}))
        reverse=defaultdict(set); byname=defaultdict(set)
        for key in functions: byname[key[1]].add(key)
        for key,fn in functions.items():
            for callee in fn['calls']:
                for target in byname[callee]:
                    reverse[target].add(key)
        # Find nearest anchored caller(s); stop a path at the first anchor.
        # This is a syntactic source graph, with recursion/indirects unresolved.
        for site in sites:
            key=(site['path'],site['function']); queue=deque([(key,0)]); seen=set(); found=set()
            while queue:
                item,depth=queue.popleft()
                if item in seen: continue
                seen.add(item)
                if item in roots:
                    found.update(roots[item]); continue
                if depth<6:
                    queue.extend((caller,depth+1) for caller in reverse[item])
            site['candidate_families']=sorted(found)
        editions.append(dict(edition=spec['edition'],revision=revision,files=files,
            function_count=len(functions),parser_error_files=errors,anchors=anchors,
            missing_anchors=missing,ui_sites=sorted(sites,key=lambda s:(s['path'],s['byte_offset'])),
            unclassified_sites=sum(not s['candidate_families'] for s in sites),
            unparsed_sites=sum(s['function'] is None for s in sites),
            indirect_calling_functions=sum('<indirect>' in f['calls'] for f in functions.values())))
    report=dict(format='fdisbull-civd-z-source-inventory-1',families=len(catalog['families']),
        source_vocabulary=sorted(UI_CALLS),editions=editions,native_screens_visited=0,
        scope='All C units scanned for a declared UI-call vocabulary. Parser gaps, indirect calls, dynamic content and native reachability remain explicit.')
    Path(output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(families=report['families'],editions=[
        dict(edition=e['edition'],functions=e['function_count'],sites=len(e['ui_sites']),
             anchors=len(e['anchors']),missing=e['missing_anchors'],unclassified=e['unclassified_sites'],
             unparsed=e['unparsed_sites']) for e in editions])))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',required=True,type=Path,help='JSON array of edition/directory objects')
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.exists(): raise ValueError('inventory output must be new')
    inventory(json.loads(args.sources.read_text()),args.output)
