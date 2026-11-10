"""Objective, opt-in QA friction reports with explicit human scope decisions.

' Salty ' is an informal tester note, not a sentiment score or an auto-approval.
No repository, verifier, user settings or actual tool implementation is changed.
"""
from __future__ import annotations

import json
import sys

FORMAT = 'fdisbull-agent-friction-1'
DECISIONS = {'go_with_it', 'do_your_best', 'stop_here'}
CLASSIFICATIONS = {'discoverability', 'defect', 'missing_capability',
                   'manual_repetition', 'unknown', 'tool_output'}


class FrictionError(ValueError):
    pass


def _string(value, label, upper=2000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= upper:
        raise FrictionError(f'{label} must be nonempty bounded text')
    return value.strip()


def validate_report(report):
    """Validate untrusted test-agent evidence, returning a sanitized copy."""
    allowed = {'format','reporter','task','tool_version','command',
               'expected','observed','classification','reproduce','evidence',
               'manual_steps','tool_calls','salty_note','proposal','scope_expansion'}
    if not isinstance(report, dict) or set(report) - allowed or (allowed - {'salty_note','proposal'}) - set(report):
        raise FrictionError('Invalid friction report fields')
    if report['format'] != FORMAT or report['classification'] not in CLASSIFICATIONS:
        raise FrictionError('Invalid report format/classification')
    for key in ('reporter','task','tool_version','command','expected','observed'):
        _string(report[key], key)
    for key in ('manual_steps','tool_calls'):
        if type(report[key]) is not int or not 0 <= report[key] <= 100000:
            raise FrictionError(f'Invalid {key} count')
    for key in ('reproduce','evidence'):
        val=report[key]
        if not isinstance(val,list) or not 1 <= len(val) <= 30:
            raise FrictionError(f'Expected 1..30 {key} entries')
        for element in val: _string(element,key,500)
    if type(report['scope_expansion']) is not bool:
        raise FrictionError('scope_expansion must be bool')
    for key in ('salty_note','proposal'):
        if key in report:
            _string(report[key],key,1000)
    return json.loads(json.dumps(report,sort_keys=True,allow_nan=False))


def triage(report, *, capability_status='unknown', human_decision=None):
    """Return a recommendation. Never silently approve a new capability."""
    report=validate_report(report)
    if capability_status not in ('unknown','available','broken','missing'):
        raise FrictionError('Invalid capability status')
    if human_decision is not None and human_decision not in DECISIONS:
        raise FrictionError('Invalid human decision')
    if capability_status == 'available':
        action='repair_skill_discoverability' if report['classification']=='discoverability' else 'investigate_usage_or_contract'
    elif capability_status == 'broken':
        action='fix_existing_capability'
    elif capability_status == 'unknown':
        action='check_capability_catalog_and_reproduce'
    elif report['scope_expansion']:
        action={'go_with_it':'implement_on_review_branch',
                'do_your_best':'continue_with_existing_tools',
                'stop_here':'park_affected_task'}.get(human_decision,'request_human_scope_decision')
    else:
        action='implement_bounded_helper_with_tests'
    return {'format':'fdisbull-agent-friction-triage-1', 'action':action,
            'requires_human_decision':capability_status=='missing' and report['scope_expansion'] and human_decision is None,
            'human_decision':human_decision, 'reporter':report['reporter'],
            'evidence':report['evidence'],
            'claim_ceiling':'QA observation and triage only; no verifier/proof or merge authorization'}


def promotion_gate(report, qa):
    """Check presence of independently observed evidence; do not claim proofs."""
    report=validate_report(report)
    required={'reviewer','reproduced','regressions_passed','original_task_resumed','evidence','notes'}
    if not isinstance(qa,dict) or set(qa)!=required:
        raise FrictionError('Invalid QA receipt')
    _string(qa['reviewer'],'QA reviewer')
    _string(qa['notes'],'QA notes')
    if qa['reviewer']==report['reporter']:
        raise FrictionError('Independent QA reporter required')
    if any(type(qa[k]) is not bool for k in ('reproduced','regressions_passed','original_task_resumed')):
        raise FrictionError('Explicit QA booleans required')
    if not isinstance(qa['evidence'],list) or not qa['evidence']:
        raise FrictionError('QA must retain independent evidence')
    for item in qa['evidence']:_string(item,'QA evidence',500)
    accepted=qa['reproduced'] and qa['regressions_passed'] and qa['original_task_resumed']
    return {'promotion_ready_for_review':accepted,
            'qualification':'independent QA claims only; human review and code/proof gates remain necessary',
            'qa_evidence':list(qa['evidence'])}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Validate a saved JSON friction report (offline)')
    parser.add_argument('report',help='path to JSON report')
    parser.add_argument('--capability-status',choices=['unknown','available','broken','missing'],default='unknown')
    parser.add_argument('--decision',choices=sorted(DECISIONS))
    args=parser.parse_args(argv)
    with open(args.report,encoding='utf8') as handle: report=json.load(handle)
    print(json.dumps(triage(report,capability_status=args.capability_status,human_decision=args.decision),indent=2))


if __name__=='__main__': main()
