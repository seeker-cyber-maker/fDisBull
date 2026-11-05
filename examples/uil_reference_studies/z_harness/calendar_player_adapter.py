"""Authored research bridge: portable calendar harness -> existing text Player.

This adds no calendar rules, native execution, renderer, or durable checkpoint.
The supplied harness remains the only state owner. Use only with its calendar
study profile; this is not a general adapter for arbitrary world/UIL formats.
"""
from __future__ import annotations


class CalendarPlayerAdapter:
    def __init__(self, harness):
        self.harness = harness
        self.action_calls = 0

    def observe(self):
        obs = self.harness.observe()
        values = obs['values']
        description = f"Turn: {values['turn']}\nYear: {values['year']}"
        return {
            'complete': True,
            'context': {'id': 'calendar-study', 'token': obs['context_token'],
                        'title': 'Calendar slice', 'description': description},
            'objects': [{'id': 'calendar', 'label': 'calendar', 'aliases': [],
                         'description': description, 'verbs': ['advance']}],
            'inventory': [], 'coverage': {'partial': True},
        }

    def act(self, request):
        if (not isinstance(request, dict)
                or set(request) != {'verb', 'target', 'item', 'context_token'}
                or request['verb'] != 'advance' or request['target'] != 'calendar'
                or request['item'] is not None):
            return {'status': 'rejected', 'complete': True,
                    'effects': 'none-confirmed', 'message': 'Unsupported calendar request.'}
        self.action_calls += 1
        result = self.harness.act({'action': 'advance-calendar-slice',
                                   'context_token': request['context_token']})
        if result['status'] == 'complete':
            values = result['observation']['values']
            return {'status': 'success', 'complete': True, 'effects': 'applied-confirmed',
                    'message': f"Turn: {values['turn']}\nYear: {values['year']}"}
        # The supplied pure harness has not committed model state in these cases.
        # This rule must NOT be generalized to native actions with partial effects.
        return {'status': 'rejected', 'complete': True, 'effects': 'none-confirmed',
                'message': result.get('reason') or 'No model state was committed.'}

    def save(self, *args, **kwargs):
        return {'status': 'unsupported', 'complete': False,
                'reason': 'Session checkpoints are not durable saves.'}

    def load(self, *args, **kwargs):
        return self.save()
