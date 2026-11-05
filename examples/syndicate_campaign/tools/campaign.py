"""Bounded, read-only campaign decoding and explicit research-kernel model.

No game files, instruction bytes, screenshots, or save writer are embedded.
The model is not a complete campaign simulator and never operates a live guest.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

MAIN_SHA256 = 'bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078'
SAVE_SIZE = 28247
FUNDING_MULTIPLIERS = (1, 2, 4, 6, 10, 15, 30, 50, 75, 100)
SECTIONS = (
    ('companies', 20, 8376, 0x5E49C),
    ('territories', 8396, 500, 0x5539C),
    ('weapon_projects', 8896, 10020, 0x57BF4),
    ('mod_projects', 18916, 8838, 0x55780),
    ('active_project', 27754, 489, 0x55594),
    ('trailer', 28243, 4, 0x60AA4),
)
STATE_NAMES = {0: 'running', 1: 'completion-pending', 2: 'idle', 3: 'insufficient-funds'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def integer(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def graph_progress(history: list[int]) -> tuple[int, int]:
    """Validate the admitted contiguous, monotonic 240-word research graph."""
    if len(history) != 240:
        raise ValueError('Research graph must have 240 samples')
    used, previous, ended = 0, 0, False
    for value in history:
        integer(value, 0, 2490, 'graph sample')
        if value == 0:
            ended = True
        else:
            if ended or value < previous:
                raise ValueError('Graph has a hole or reverses; outside this model profile')
            used += 1
            previous = value
    return previous, used


def decode_save(data: bytes, *, source_sha256: str, selected_company: int = 0) -> dict:
    """Decode this release's structure; a parse is NOT original-loader acceptance."""
    if source_sha256 != MAIN_SHA256:
        raise ValueError('Unqualified executable identity')
    if not isinstance(data, bytes) or len(data) != SAVE_SIZE:
        raise ValueError(f'This profile requires exactly {SAVE_SIZE} bytes')
    integer(selected_company, 0, 7, 'selected_company')
    companies = []
    for i in range(8):
        offset = 20 + 1047 * i
        cash, day_ticks, day, year = struct.unpack_from('<IIHH', data, offset)
        companies.append({'id': i, 'cash': cash, 'within_day_ticks_raw': day_ticks,
                          'day_raw': day, 'year_raw': year})
    territories = []
    for i in range(50):
        offset = 8396 + i * 10
        status, owner, tax_a, tax_b, unknown, population = struct.unpack_from('<HBBBBI', data, offset)
        integer(owner, 0, 7, 'territory owner')
        territories.append({'id': i, 'status_raw': status, 'owner_raw': owner,
                            'tax_a_raw': tax_a, 'tax_b_raw': tax_b,
                            'unknown_byte': unknown, 'population': population})
    projects = {}
    for family, offset, count, stride, cost_at, progress_at, history_at, next_at in (
        ('weapon', 8896, 20, 501, 13, 17, 19, 499),
        ('mod', 18916, 18, 491, 6, 8, 10, 490),
    ):
        rows = []
        for i in range(count):
            record = data[offset + i * stride:offset + (i + 1) * stride]
            nxt = record[next_at]
            integer(nxt, 0, count - 1, 'next project')
            progress = struct.unpack_from('<h', record, progress_at)[0]
            if progress != -1 and not 0 <= progress <= 2400:
                raise ValueError('Project progress outside qualified profile')
            rows.append({'id': i, 'code': record[0],
                         'price_signed': struct.unpack_from('<i', record, 1)[0],
                         'base_hourly_cost': struct.unpack_from('<H', record, cost_at)[0],
                         'stored_progress': progress,
                         'history': list(struct.unpack_from('<240H', record, history_at)),
                         'next_project': nxt,
                         'category_raw': record[500] if family == 'weapon' else i // 3,
                         'level': None if family == 'weapon' else i % 3 + 1,
                         'disabled_record': record[0] == 254})
        projects[family] = rows
    a = data[27754:28243]
    state, kind, project = a[:3]
    if state not in STATE_NAMES or kind not in (0, 1, 2):
        raise ValueError('Unknown active-project state or kind')
    if kind:
        integer(project, 0, 17 if kind == 1 else 19, 'active project')
    rate, base = struct.unpack_from('<iH', a, 3)
    integer(rate, -1, 9, 'funding index')
    history = list(struct.unpack_from('<240H', a, 9))
    progress, used = graph_progress(history)
    return {
        'format': 'syndicate-campaign-observation-1',
        'source_sha256': source_sha256,
        'save_sha256': digest(data), 'save_size': len(data),
        'selected_company': selected_company,
        'selection_provenance': 'explicit caller context; not serialized in this save',
        'qualification': 'parsed-selected-edition; native compatibility requires separate receipt',
        'companies': companies, 'territories': territories, 'projects': projects,
        'active': {'state': state, 'state_name': STATE_NAMES[state], 'kind': kind,
                   'project': project, 'funding_index': rate, 'base_hourly_cost': base,
                   'history': history, 'progress': progress, 'samples': used},
        'uninterpreted': ['company fields beyond first 12 bytes', 'territory state policy beyond admission',
                          'other weapon/mod payload fields', 'four-byte trailer', 'label semantics'],
    }


def family_name(kind: int) -> str:
    if kind not in (1, 2):
        raise ValueError('An active mod/weapon kind is required')
    return 'mod' if kind == 1 else 'weapon'


def effective_progress(campaign: dict, family: str, index: int) -> int:
    record = campaign['projects'][family][index]
    active = campaign['active']
    if active['kind'] in (1, 2) and family_name(active['kind']) == family and active['project'] == index:
        # The active graph can be newer than the per-project saved progress word.
        return graph_progress(active['history'])[0]
    return record['stored_progress']


def funding_rows(base: int) -> list[dict]:
    integer(base, 0, 65535, 'base hourly cost')
    return [{'index': i, 'hourly_charge': base * multiplier,
             'display_daily_charge': 24 * base * multiplier,
             'progress_per_hour': 10 * (i + 1)}
            for i, multiplier in enumerate(FUNDING_MULTIPLIERS)]


def research_tick(campaign: dict) -> dict:
    """Model source 0x35E20 at its return boundary, NOT its caller/finalizer.

    State flags are not auto-updated: the original caller consumes return AL.
    Out-of-profile graphs fail before mutation. Clock advancement, taxes, UI,
    unrelated actors, I/O and native scheduling are not simulated.
    """
    result = deepcopy(campaign)
    a = result['active']
    if a['kind'] == 0:
        return {'return_al': 2, 'charged': 0, 'campaign': result}
    family = family_name(a['kind'])
    rate = integer(a['funding_index'], -1, 9, 'funding index')
    if rate == -1:
        return {'return_al': 0, 'charged': 0, 'campaign': result}
    previous, used = graph_progress(a['history'])
    if used >= 240 or previous >= 2400:
        raise ValueError('No qualified unfinished graph slot; do not normalize an overflow')
    base = integer(a['base_hourly_cost'], 0, 65535, 'hourly base')
    company = result['companies'][result['selected_company']]
    cash = integer(company['cash'], 0, 0xffffffff, 'cash')
    charge = base * FUNDING_MULTIPLIERS[rate]
    if charge > cash:
        return {'return_al': 3, 'charged': 0, 'campaign': result}
    company['cash'] = cash - charge
    new = (previous + 10 * (rate + 1)) & 0xffff
    a['history'][used] = new
    a['progress'], a['samples'] = new, used + 1
    status = 0
    if new >= 2400:
        status = 1
        rec = result['projects'][family][a['project']]
        rec['stored_progress'] = 2400
        rec['history'] = a['history'][:]
        nxt = rec['next_project']
        if nxt and result['projects'][family][nxt]['stored_progress'] == -1:
            result['projects'][family][nxt]['stored_progress'] = 0
    return {'return_al': status, 'charged': charge, 'campaign': result}


def finalize_completed(campaign: dict) -> dict:
    """Qualified completion use of source 0x36190, separate from hourly charge."""
    result = deepcopy(campaign)
    a = result['active']
    family = family_name(a['kind'])
    rec = result['projects'][family][a['project']]
    if graph_progress(a['history'])[0] < 2400 or rec['stored_progress'] != 2400:
        raise ValueError('Completion has not been established')
    rec['history'] = a['history'][:]
    if family == 'weapon' and rec['price_signed'] < 0:
        if rec['price_signed'] == -2147483648:
            raise ValueError('INT_MIN price outside admitted completion profile')
        rec['price_signed'] = -rec['price_signed']
    result['active'] = {'state': 2, 'state_name': 'idle', 'kind': 0, 'project': 0,
                        'funding_index': -1, 'base_hourly_cost': 0,
                        'history': [0] * 240, 'progress': 0, 'samples': 0}
    return result


def available(campaign: dict, catalog: dict, territory: int, *, override: bool | None) -> bool | None:
    """The directed original admission helper, not an unconstrained mission launch."""
    integer(territory, 0, 49, 'territory')
    if catalog['source_sha256'] != campaign['source_sha256']:
        raise ValueError('Catalog/campaign source mismatch')
    if override is None:
        return None  # This runtime flag is not serialized in the save.
    if type(override) is not bool:
        raise ValueError('override must be bool or unknown')
    if override:
        return True
    company = campaign['selected_company']
    t = campaign['territories'][territory]
    if t['owner_raw'] == company and t['status_raw'] != 255:
        return False
    if catalog['territories'][territory]['mission_number'] == 1 or t['status_raw'] == 255:
        return True
    return any(t['owner_raw'] == company and t['status_raw'] != 255 and
               territory in catalog['territories'][t['id']]['outgoing']
               for t in campaign['territories'])


def project_label(catalog: dict, family: str, index: int) -> str:
    return catalog['projects'][family][index]['label']


def render(campaign: dict, catalog: dict, *, view: str = 'research', override: bool | None = None) -> str:
    """Human/agent text view. Observer selection is not original-game input."""
    if catalog['source_sha256'] != campaign['source_sha256']:
        raise ValueError('Source mismatch')
    company = campaign['companies'][campaign['selected_company']]
    lines = [f'SYNDICATE CAMPAIGN | {view.upper()} | cash {company["cash"]}',
             'Recorded semantic view; no game time advances and no native actions are sent.']
    if view == 'world':
        lines += ['ID  TERRITORY                  MISSION  ADMISSION',
                  'Admission is a directed progression rule, not geographic proximity.']
        for t in catalog['territories']:
            ok = available(campaign, catalog, t['id'], override=override)
            state = 'unknown flag' if ok is None else ('available' if ok else 'not available')
            lines.append(f'{t["id"]:02d}  {t["label"]:<26} {t["mission_number"]:>3}      {state}')
        lines += ['Unowned territory tax and owner remain hidden in this public-style projection.',
                  'Diagnostic raw records are separately available; this is not a full visibility model.']
    elif view in ('research', 'mods', 'equipment'):
        a = campaign['active']
        lines.append(f'Active: {a["state_name"]}')
        if a['kind']:
            family = family_name(a['kind'])
            lines.append(f'{project_label(catalog,family,a["project"])}: {a["progress"]}/2400; '
                         f'{a["progress"]/24:.2f}% threshold progress')
            if a['funding_index'] >= 0:
                row = funding_rows(a['base_hourly_cost'])[a['funding_index']]
                lines.append(f'Funding {row["index"]}: {row["hourly_charge"]}/hour; '
                             f'{row["display_daily_charge"]}/day; +{row["progress_per_hour"]} points/hour')
            else:
                lines.append('Funding paused (-1).')
        families = ('mod',) if view == 'mods' else ('weapon',) if view == 'equipment' else ('weapon', 'mod')
        for family in families:
            lines.append(f'{family.upper()} PROJECTS')
            for rec in campaign['projects'][family]:
                if rec['disabled_record']:
                    continue
                progress = effective_progress(campaign, family, rec['id'])
                state = 'locked' if progress == -1 else 'complete' if progress >= 2400 else f'{progress}/2400'
                lines.append(f'{family}-{rec["id"]:02d} {project_label(catalog,family,rec["id"]):<20} {state}')
        # Compact data graph, not a claim to replicate original pixels.
        used = a['samples']
        if used:
            samples = a['history'][:used]
            lines.append('RECORDED HOURLY GRAPH: ' + ' '.join(str(v) for v in samples[-24:]))
        lines.append('Completion, active graph, unlocks and equipment price are separate state fields.')
    else:
        raise ValueError('Unknown view')
    return '\n'.join(lines)


class CampaignProvider:
    """Read-only backend for the actual existing fDisBull Player protocol."""
    def __init__(self, campaign: dict, catalog: dict, *, override: bool | None = None):
        self.campaign, self.catalog, self.override = deepcopy(campaign), deepcopy(catalog), override
        self.token = digest(json.dumps([self.campaign,self.catalog,override],sort_keys=True).encode())

    def observe(self) -> dict:
        objects = [{'id': v, 'label': v, 'aliases': aliases, 'verbs': [],
                    'description': render(self.campaign,self.catalog,view=v,override=self.override)}
                   for v, aliases in [('world',['mission selection','missions']),
                                      ('research',['research tab','research graph']),
                                      ('mods',['modifications']),('equipment',['weapons'])]]
        return {'complete': True, 'context': {'id':'syndicate-campaign-recorded','token':self.token,
                'title':'Syndicate campaign review', 'description':'Mission selection, equipment and research projections. Original input is not connected.'},
                'coverage':{'partial':True},'objects':objects,'inventory':[]}

    def act(self, request: dict) -> dict:
        return {'status':'rejected','complete':True,'effects':'none-confirmed',
                'message':'This recorded campaign view does not launch missions, spend money or rewrite saves.'}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--save',type=Path,required=True)
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--source-sha256',required=True)
    ap.add_argument('--company',type=int,default=0)
    ap.add_argument('--view',choices=['world','research','mods','equipment'],default='research')
    ap.add_argument('--observed-no-override',action='store_true',help='Explicit external observation, not inferred from a save')
    args = ap.parse_args()
    data = args.save.read_bytes()
    campaign = decode_save(data,source_sha256=args.source_sha256,selected_company=args.company)
    catalog = json.loads(args.catalog.read_text())
    print(render(campaign,catalog,view=args.view,override=False if args.observed_no_override else None))


if __name__ == '__main__':
    main()
