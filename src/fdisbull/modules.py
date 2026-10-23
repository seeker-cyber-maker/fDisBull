"""Explicit, offline module analysis. No DLL is loaded into a process."""
import json
from pathlib import Path


def analyze_module(path,project,export=None,entry=None,max_instructions=10000):
    from .inspection import inspect_binary
    from .loader import load_image
    from .project import Project,integer,number
    budget=integer(max_instructions,'max_instructions',1,1_000_000)
    if export is not None and entry is not None:
        raise ValueError('select an export or an entry, not both')
    if export is not None and (not isinstance(export,(str,int)) or isinstance(export,bool)):
        raise ValueError('export must be a name or integer ordinal')
    if entry is not None:
        entry=number(entry)
    source=Path(path)
    # Validate the selection before creating a persistent database.
    image=load_image(source,module=True,entry=entry)
    document=inspect_binary(image.source_bytes)
    selected=entry
    selected_export=None
    if export is not None:
        ordinal=int(export[1:]) if isinstance(export,str) and export.startswith('#') and export[1:].isdigit() else export if isinstance(export,int) else None
        matches=[item for item in document.get('exports',[]) if (item.get('ordinal')==ordinal if ordinal is not None else item.get('name')==export)]
        if not matches:
            raise ValueError('requested export was not found')
        if any(item.get('forwarder') for item in matches):
            raise ValueError('requested export is forwarded; select its destination module explicitly')
        addresses={item.get('address') for item in matches}
        if len(addresses)!=1 or None in addresses:
            raise ValueError('requested export has no unique mapped address')
        selected=addresses.pop()
        selected_export=matches[0]
        if not any(r.executable and r.start<=selected<r.start+len(r.data) for r in image.regions):
            raise ValueError('requested export is not in executable mapped bytes')
    with Project._create_image(project,source.name,image) as db:
        if selected is not None:
            with db.transaction(True):
                db.meta['analysis_roots']=[selected]
                db.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('analysis_roots',json.dumps([selected])))
                db._reset_analysis(1)
        analysis=db.analyze(max_instructions=budget)
        return {'project':str(db.path),'module':source.name,'selected_export':selected_export,
                'analysis_roots':[hex(selected)] if selected is not None else None,
                'analysis':analysis,'status':db.status(),
                'scope':'Offline module snapshot; imports and forwarded exports do not load other DLLs.'}
