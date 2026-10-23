"""Read-only call targets and incoming call-site evidence from stored analysis."""
import json

_SITE_LIMIT = 100


def _hx(address):
    return f'0x{address:x}'


def _segmented(address, context):
    if context and ':cs=' in context:
        selector = int(context.rsplit('=', 1)[1], 16)
        offset = address - selector * 16
        if 0 <= offset <= 0xFFFF:
            return f'{selector:04x}:{offset:04x}'
    return None


def _import_aliases(rows):
    # Recovered identities supersede the on-disk import directory, while all
    # alternatives within that recovery remain visible.
    recovered = [row for row in rows if row['kind'] == 'recovered_import']
    aliases = {}
    for row in recovered or rows:
        detail = json.loads(row['detail'])
        for item in detail.get('alternatives', [detail]):
            alias = dict(module=item.get('module') or row['module'] or None,
                         name=item.get('name'), ordinal=item.get('ordinal'),
                         forwarder=item.get('forwarder'))
            identity = (alias['module'], alias['name'], alias['ordinal'], alias['forwarder'])
            aliases[identity] = alias
    return sorted(aliases.values(), key=lambda item: (item['module'] or '', item['name'] or '',
                                                     -1 if item['ordinal'] is None else item['ordinal']))


class CallViewsMixin:
    def calls(self, version=None, limit=200, offset=0, kind='all'):
        """Group stored call sites; never execute code or infer caller ownership."""
        from .project import integer
        limit = integer(limit, 'limit', 1, 10000)
        offset = integer(offset, 'offset', 0, (1 << 63) - 1)
        if kind not in ('all', 'function', 'library', 'unresolved'):
            raise ValueError('kind must be all, function, library or unresolved')
        with self.transaction():
            v = self.version(version)['id']
            dos = self.meta['format'] == 'MZ'

            def label(address, context=None):
                return self._dos_label(v, address, context) if dos else self._label(v, address)

            targets = {}
            if dos:
                rows = self.db.execute("SELECT * FROM dos_edges WHERE version=? AND kind='call' ORDER BY source,source_context,target,target_context", (v,))
                for row in rows:
                    targets.setdefault((row['source_context'], row['source']), []).append(
                        dict(target=row['target'], context=row['target_context'] or None, kind='call', evidence=row['evidence']))
            else:
                rows = self.db.execute("SELECT * FROM xrefs WHERE version=? AND kind IN ('call','resolved_call') ORDER BY source,context,target,kind", (v,))
                for row in rows:
                    targets.setdefault((row['context'], row['source']), []).append(
                        dict(target=row['target'], context=self.context, kind=row['kind'], evidence=row['evidence']))
            imports = {}
            for row in self.db.execute("SELECT * FROM symbols WHERE version=? AND kind IN ('imports','recovered_import') ORDER BY address,kind,module,name", (v,)):
                imports.setdefault(row['address'], []).append(row)
            references = {}
            for row in self.db.execute("SELECT o.* FROM operand_refs o JOIN instructions i ON i.version=o.version AND i.context=o.context AND i.address=o.source WHERE o.version=? AND i.flow='indirect_call' AND o.role='memory' ORDER BY o.source,o.context,o.target", (v,)):
                references.setdefault((row['context'], row['source']), []).append(row)
            groups, all_sites = {}, set()

            def add(group_kind, target, context, row, evidence, slot_symbols=None):
                source = int(row['address'], 16)
                source_id = (row['context'], row['address'])
                identity = (group_kind, target, context, source_id if group_kind == 'unresolved' else None)
                if identity not in groups:
                    aliases = _import_aliases(slot_symbols) if slot_symbols else []
                    modules = sorted({item['module'] for item in aliases if item['module']})
                    names = sorted({item['name'] for item in aliases if item['name']})
                    ordinals = {item['ordinal'] for item in aliases}
                    module = modules[0] if len(modules) == 1 else None
                    name = label(target, context) if target is not None else 'unresolved_call_at_' + (_segmented(source, row['context']) or _hx(source))
                    groups[identity] = dict(kind=group_kind, target=_hx(target) if target is not None else None,
                        target_context=context, target_segmented_address=_segmented(target, context) if target is not None else None,
                        target_kind='import_slot' if group_kind == 'library' else 'code_address' if target is not None else 'unknown',
                        name=name, function=('|'.join(names) if names else None) if group_kind == 'library' else name if group_kind == 'function' else None,
                        library=module, module=module, modules=modules,
                        ordinal=next(iter(ordinals)) if len(ordinals) == 1 else None, aliases=aliases,
                        status='static_evidence', runtime_observed=False, function_boundary_proven=False,
                        call_site_count=0, call_sites=[], call_sites_truncated=False,
                        _seen=set(), _stored={}, _sort=(0 if group_kind == 'function' else 1 if group_kind == 'library' else 2,
                                                       target if target is not None else source, context or '', row['context']))
                group = groups[identity]
                all_sites.add(source_id)
                if source_id not in group['_seen']:
                    group['_seen'].add(source_id)
                    group['call_site_count'] += 1
                    if len(group['call_sites']) < _SITE_LIMIT:
                        resolved = [dict(target=_hx(int(item['target'], 16)), target_context=item['context'], kind=item['kind'],
                                         target_segmented_address=_segmented(int(item['target'], 16), item['context']),
                                         evidence=item['evidence']) for item in targets.get(source_id, [])]
                        site = dict(address=_hx(source), context=row['context'], segmented_address=_segmented(source, row['context']),
                                    name=label(source, row['context']), mnemonic=row['mnemonic'], flow=row['flow'], raw_operands=row['operands'],
                                    evidence=[], resolved_targets=resolved,
                                    memory_operands=[dict(address=_hx(int(ref['target'], 16)), name=label(int(ref['target'], 16)),
                                                          width=ref['width']) for ref in references.get(source_id, [])])
                        group['call_sites'].append(site)
                        group['_stored'][source_id] = site
                    else:
                        group['call_sites_truncated'] = True
                site = group['_stored'].get(source_id)
                if site is not None and evidence not in site['evidence']:
                    site['evidence'].append(evidence)

            for row in self.db.execute("SELECT * FROM instructions WHERE version=? AND flow IN ('call','indirect_call') ORDER BY address,context", (v,)):
                identity = (row['context'], row['address'])
                library_slots = {ref['target'] for ref in references.get(identity, []) if ref['target'] in imports}
                if library_slots:
                    for slot in sorted(library_slots):
                        add('library', int(slot, 16), None, row,
                            'decoded indirect call through a slot identified by import metadata', imports[slot])
                elif targets.get(identity):
                    for target in targets[identity]:
                        add('function', int(target['target'], 16), target['context'], row, target['evidence'])
                else:
                    add('unresolved', None, None, row, 'decoded call instruction; no stored target or identified import slot')
            selected = sorted((group for group in groups.values() if kind == 'all' or group['kind'] == kind), key=lambda group: group['_sort'])
            selected_sites = set().union(*(group['_seen'] for group in selected)) if selected else set()
            page = []
            for group in selected[offset:offset + limit]:
                page.append({key: value for key, value in group.items() if not key.startswith('_')})
            return dict(version=v, items=page, total=len(selected), offset=offset, has_more=offset + limit < len(selected),
                        total_call_sites=len(selected_sites), all_call_sites=len(all_sites), call_site_limit=_SITE_LIMIT,
                        analysis=self.analysis_status(v),
                        note='Stored static calls only; no runtime completeness or caller-function ownership is claimed. Alternative targets may share a call site. Library identity requires import metadata; calls through unlinked stubs remain function targets.')
