"""Link a prior two-point diagnostic after independent source discovery.

This example-only record never grants an action or upgrades a mask to native
reachability. Hash checks bind a historical witness, not arbitrary authenticity.
"""
from copy import deepcopy


WITNESS = {
    'format': 'fdisbull-recorded-agi-boundary-witness-1',
    'status': 'prior-source-bound-restored-branch-pair',
    'source': {
        'agi_sha256': '5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74',
        'object_sha256': '2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985',
        'logic': 51,
        'resource_sha256': '342d5e3e5818449162fcaed9e056fd997693e7f9429150a3ea85533a32288580',
    },
    'source_if_offsets': {'inside': 0x3df, 'outside': 0x432},
    'source_picture_sha256': 'dc2b9e40b18f474bb8fb39b9fe2850470df51747717f95620678249f85567ded',
    'context': {'variable': 75, 'value': 0},
    'observed_points': [
        {'branch': 'inside', 'origin': [130, 166], 'score_before': 15,
         'score_after': 13, 'water_consumed': True},
        {'branch': 'outside', 'origin': [130, 167], 'score_before': 15,
         'score_after': 20, 'water_consumed': True},
    ],
    'evidence': {
        'path': 'docs/evidence/agi-boundary-exceptions-2026-11-01/native-pair.json',
        'sha256': '4ff1eb638bdc9694da9b9d62844bc1d46569b8ac4724fed96412803bc5b7772f',
    },
    'scope': 'Historical two-point observation in independent supported-restore forks; not execution by this export, a reachable-world mask, completed retreat or a throwing-radius claim. Dragon poses differ between forks.',
}


def recorded_boundary_witness(report, *, agi_sha256, object_sha256):
    """Attach reviewed history only to the matching complete derived pattern."""
    expected = WITNESS['source']
    if (agi_sha256 != expected['agi_sha256'] or object_sha256 != expected['object_sha256']
            or report.get('complete') is not True
            or report.get('format') != 'fdisbull-agi-spatial-predicates-1'
            or report.get('source') != {key: expected[key] for key in ('logic', 'resource_sha256')}
            or report.get('domain') != {'width': 160, 'height': 168}):
        return None
    for finding in report.get('findings', []):
        if (finding.get('inside_if_offset') != 0x3df or finding.get('outside_if_offset') != 0x432
                or finding.get('arguments') != [0, 105, 96, 145, 166]
                or finding.get('convention') != 'inclusive'
                or finding.get('source_picture_sha256') != WITNESS['source_picture_sha256']):
            continue
        context = finding.get('shared_scalar_context', {})
        if context.get('matches_supplied_state') is not True or context.get('conditions') != [
                {'opcode': 1, 'arguments': [75, 0], 'negated': False,
                 'supplied_value': 0, 'matches': True}]:
            continue
        water = [value for value in finding.get('action_contrasts', []) if value.get('item') == 26]
        if not any(value.get('inside', {}).get('complete') is True
                   and value.get('outside', {}).get('complete') is True
                   and value['inside'].get('linear_score_delta') == -2
                   and value['outside'].get('linear_score_delta') == 5 for value in water):
            continue
        for value in finding.get('bands', []):
            band = value.get('predicate_band', {})
            if (band.get('complete') is True and band.get('direction') == 'down'
                    and band.get('thickness') == 1 and band.get('count') == 41
                    and band.get('row_runs') == [[167, 105, 146]]):
                return deepcopy(WITNESS)
    return None


def describe_recorded_boundary(witness):
    """Keep historical confirmation separate from this export's static audit."""
    if witness is None:
        return ''
    return ('Historical DOS diagnostics for this source confirmed water loss at (130, 166) '
            'and the successful water branch at (130, 167), in two independent restored tests. '
            'The other band origins remain unqualified.')
