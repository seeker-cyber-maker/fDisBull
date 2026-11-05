"""Pure, bounded models recovered from the selected Syndicate MAIN.EXE.

No game bytes, target mutation, pathfinding authority or arbitrary-width arithmetic.
These models explain source predicates. Live probes are separate evidence.
"""
from __future__ import annotations

def _position(value):
    if not isinstance(value,(tuple,list)) or len(value)!=3 or any(type(v) is not int for v in value):
        raise ValueError('Expected three exact integer coordinates')
    if not all(0<=v<32768 for v in value):
        raise ValueError('Outside admitted nonnegative signed-word domain')
    return tuple(value)

def door_person_candidate(center, person, *, kind=1, excluded=False, role_word=2, role_mask=0xffff):
    """Selected 256-cube call into the original 3x3 root-list search.

    Restricts the footprint away from map edges, where flat-index wrapping needs
    separate qualification. Do not simplify the root lookup into a rectangle:
    a fine-distance match can be absent from its three scanned root columns.
    """
    x,y,z=_position(center);px,py,pz=_position(person)
    if not (512<=x<125*256 and 512<=y<93*256):
        raise ValueError('Door edge/wrap profile is unqualified')
    for v in (role_word,role_mask):
        if type(v) is not int or not 0<=v<=0xffff:raise ValueError('Expected word mask')
    sx=(x-128-256)>>8;sy=(y-128-256)>>8
    scanned=sx<=(px>>8)<=sx+2 and sy<=(py>>8)<=sy+2
    narrow=(px+32>=x-128 and px-32<=x+128 and py+32>=y-128 and py-32<=y+128
            and pz+256>=z and pz<=z+256)
    filters=kind==1 and not excluded and bool(role_word&role_mask)
    return {'candidate':bool(scanned and narrow and filters),'root_lookup_match':scanned,
            'fine_distance_match':narrow,'person_filter_match':filters,
            'root_columns':[sx,sx+1,sx+2],'root_rows':[sy,sy+1,sy+2],
            'scope':'source-derived trigger candidate, not movement or clearance'}

def boarding_distance_gate(person,vehicle):
    """Source helper uses max(abs(dx),abs(dy)), not Euclidean distance.

    The selected nonwrapping domain preserves the original strict XY <128 and
    inclusive |dz| <=128. This alone does not admit a request: native state,
    role, vehicle flags, orders, and occupant relationships are separate gates.
    """
    p=_position(person);v=_position(vehicle)
    d=[abs(a-b) for a,b in zip(p,v)]
    if any(x>=32768 for x in d):raise ValueError('Word-wrap domain not admitted')
    return {'distance_gate':max(d[:2])<128 and d[2]<=128,
            'max_xy_raw':max(d[:2]),'delta_z_raw':d[2],
            'scope':'source-derived distance gate only, not boarding permission'}
