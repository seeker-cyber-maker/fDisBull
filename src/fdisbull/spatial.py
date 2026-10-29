"""Project and native-session integration for evidence-bound room maps."""
from copy import deepcopy
from pathlib import Path

from .spatial_map import (save_spatial_map, load_spatial_map, spatial_check,
                          candidate_points, plan_route, render_spatial_map)
from .runtime_observations import capture_observations
from .movement import matches, validate_predicate
from .operation_budget import rpc_budget


def validate_mode(mode, fair_play=False):
    if mode not in ('physical', 'assisted', 'story') or type(fair_play) is not bool:
        raise ValueError('Expected physical, assisted or story spatial mode')
    if fair_play and mode != 'physical':
        raise ValueError('Fair play requires physical mode')


def _map_context(session, document):
    """Recheck the pinned scene predicates; they do not prove all map cells."""
    revision = document['source']['context']
    handle = session.scene(revision)
    if getattr(handle, 'revision', None) != revision:
        raise ValueError('Map scene revision is unavailable or changed')
    result = handle.check()
    if not isinstance(result, dict) or result.get('complete') is not True or result.get('scene_matched') is not True:
        raise ValueError('Map scene context is unqualified')
    content = result.get('content', {})
    if not isinstance(content, dict) or any(content.get(k) is not True for k in ('requested','displayed') if k in content):
        raise ValueError('Map scene content is unqualified')
    # A moving actor may make a scene's readiness predicate false even when
    # the room and displayed content still identify the same scene.
    if result.get('status') != 'matched' and not (result.get('status') == 'mismatch' and content.get('ready') is False):
        raise ValueError('Map scene context is ambiguous or blocked')
    return result


class SpatialProjectMixin:
    def debug_save_spatial_map(self, name, document, *, parent=None, version=None, author='agent'):
        return save_spatial_map(self, name, document, parent=parent, version=version, author=author)

    def debug_spatial_map_info(self, revision, *, version=None):
        return load_spatial_map(self, revision, version=version)

    def debug_spatial_check(self, revision, point, *, conditions=None, version=None):
        doc = load_spatial_map(self, revision, version=version)['document']
        return spatial_check(doc, point, conditions=conditions)

    def debug_spatial_candidates(self, revision, *, version=None, **options):
        doc = load_spatial_map(self, revision, version=version)['document']
        return candidate_points(doc, **options)

    def debug_spatial_route(self, revision, start, goal, *, version=None, **options):
        doc = load_spatial_map(self, revision, version=version)['document']
        return plan_route(doc, start, goal, **options)

    def debug_spatial_overlay(self, revision, output, *, conditions=None, version=None):
        info = load_spatial_map(self, revision, version=version)
        result = render_spatial_map(info['document'], conditions=conditions)
        path = Path(output).expanduser().resolve()
        with path.open('xb') as stream:
            stream.write(result.pop('png'))
        return dict(result, path=str(path), revision=info['id'], sha256=info['sha256'])


class SpatialSessionMixin:
    def spatial_navigation(self, revision, *, observations, room_field='room', conditions=None):
        return SpatialNavigationHandle(self, revision, observations, room_field=room_field, conditions=conditions)

    def spatial_policy(self, mode=None, *, fair_play=None):
        current = getattr(self, '_spatial_mode', 'assisted')
        locked = getattr(self, '_fair_play', False)
        mode = current if mode is None else mode
        fair_play = locked if fair_play is None else fair_play
        if locked and (not fair_play or mode != 'physical'):
            raise ValueError('Fair play cannot be disabled within this session')
        validate_mode(mode, fair_play)
        self._spatial_mode, self._fair_play = mode, fair_play
        self._allow_assisted_travel = mode == 'assisted' and not fair_play
        policy = {'spatial_mode':mode, 'fair_play':fair_play,
                  'assisted_travel':self._allow_assisted_travel, 'voluntary':True}
        self._event('spatial-policy', policy)
        return policy

    @rpc_budget
    def spatial_action(self, map_revision, definition, *, room_field='room', conditions=None,
                       zone=None, actor_recipe=None, travel_plan=None, timeout_ms=10000):
        """Send original input under a selected spatial policy and pinned map.

        Conditions are fresh observation predicates, never cached booleans.
        Assisted placement is limited to a declared actor recipe. Story guard
        authority belongs to the action definition, not to object labels.
        """
        from .spatial_modes import SpatialActionHandle
        if getattr(self, '_spatial_guard_failed', False):
            raise ValueError('Session is unusable after uncertain guard restoration')
        info = load_spatial_map(self.project, map_revision, version=self.version['id'])
        doc = info['document']
        observations = definition['observations']
        if room_field not in observations:
            raise ValueError('Map requires an observed room field')
        predicates = {} if conditions is None else deepcopy(conditions)
        if not isinstance(predicates, dict):
            raise ValueError('Map conditions require named predicates')
        for predicate in predicates.values():
            validate_predicate(predicate, observations)

        def fresh():
            _map_context(self, doc)
            observed = capture_observations(self, observations)
            if observed.get('complete') is not True:
                raise ValueError('Map context observation incomplete')
            if str(observed['values'][room_field]) != doc['source']['room'] or not matches(definition['context'], observed['values']):
                raise ValueError('Map room or action context changed')
            return observed, {key:matches(value, observed['values']) for key,value in predicates.items()}

        def check(revision, point):
            if revision != info['id']:
                raise ValueError('Map revision changed')
            _, states = fresh()
            return spatial_check(doc, point, conditions=states)

        def anchor(revision, action, observed):
            if not isinstance(zone, str):
                raise ValueError('Assistance requires a named object interaction zone')
            _, states = fresh()
            layer = next((l for l in doc['layers'] if l['id'] == zone and l['kind'] == 'object'), None)
            if layer is None:
                raise ValueError('Unknown object zone')
            if 'when' in layer and states.get(layer['when']) is not True:
                raise ValueError('Object interaction zone is inactive or unqualified')
            # Explicit, evidence-linked points take priority over geometric
            # suggestions. Every selected point still passes the full mask.
            choices = layer.get('interaction_points') or candidate_points(doc, zone=zone, limit=32, conditions=states)
            for point in choices:
                if spatial_check(doc, point, conditions=states)['classification'] == 'clear':
                    return point
            raise ValueError('No qualified clear interaction anchor')

        def placement(action, point, observed):
            plan = deepcopy(travel_plan)
            if not isinstance(plan, dict) or not isinstance(actor_recipe, dict):
                raise ValueError('Qualified placement recipe required')
            plan['writes'] = [dict(actor_recipe[axis], value=value) for axis,value in zip(('x','y'),point)] + deepcopy(actor_recipe['refresh'])
            return plan

        observed, _ = fresh()
        bound_definition = deepcopy(definition)
        bound_definition['context'] = {'all':[deepcopy(definition['context']),
            {'field':room_field,'op':'eq','value':observed['values'][room_field]}]}
        return SpatialActionHandle(self, info['id'], mode=getattr(self, '_spatial_mode', 'assisted'),
            fair_play=getattr(self, '_fair_play', False), check_point=check, choose_anchor=anchor,
            travel_plan=placement, actor_recipe=actor_recipe,
            qualify_context=lambda: {'qualified':True, 'scene':_map_context(self, doc)}).interact(bound_definition, timeout_ms=timeout_ms)


class SpatialNavigationHandle:
    """Fresh room/condition adapter for the existing bounded movement loop."""
    def __init__(self, session, revision, observations, *, room_field='room', conditions=None):
        from .runtime_observations import validate_observations
        validate_observations(observations)
        if room_field not in observations:
            raise ValueError('Spatial navigation requires an observed room')
        self.session, self.observations, self.room_field = session, deepcopy(observations), room_field
        self.info = load_spatial_map(session.project, revision, version=session.version['id'])
        self.conditions = {} if conditions is None else deepcopy(conditions)
        if not isinstance(self.conditions, dict):
            raise ValueError('Spatial conditions require named predicates')
        for predicate in self.conditions.values(): validate_predicate(predicate, observations)

    def navigation_check(self, point):
        # Reauthenticate the persisted revision as well as the live context.
        current = load_spatial_map(self.session.project, self.info['id'], version=self.session.version['id'])
        if current['sha256'] != self.info['sha256']:
            raise ValueError('Spatial map changed')
        states = {}
        try:
            context = _map_context(self.session, current['document'])
        except Exception as error:
            return {'classification':'unknown','conditions':states,'manifest_sha256':current['sha256'],
                    'reason':'map_context_unqualified','error':str(error)}
        observed = capture_observations(self.session, self.observations)
        if observed.get('complete') is not True or str(observed.get('values',{}).get(self.room_field)) != current['document']['source']['room']:
            return {'classification':'unknown','conditions':states,'observation':observed,
                    'manifest_sha256':current['sha256'],'reason':'map_context_unqualified'}
        states = {key:matches(predicate, observed['values']) for key,predicate in self.conditions.items()}
        return spatial_check(current['document'], point, conditions=states) | {
            'conditions':states,'observation':observed,'scene_context':context,'manifest_sha256':current['sha256'],'map_revision':current['id']}

    def first_boundary(self, start, target, *, conditions=None):
        from .spatial_map import _compile, _check
        document=self.info['document']; compiled=_compile(document, conditions)
        # The movement adapter already validates integer in-map endpoints. This
        # samples each game unit on the straight intended segment; it is not a
        # path planner or a promise that the engine follows this segment.
        steps=max(abs(target[0]-start[0]),abs(target[1]-start[1]))
        if steps > 65536: raise ValueError('Boundary check exceeds its budget')
        for index in range(steps+1):
            point=[round(start[axis]+(target[axis]-start[axis])*index/steps) if steps else start[axis] for axis in (0,1)]
            checked=_check(document, point, compiled)
            if checked['classification'] != 'clear': return {'result':checked,'step':index}
        return None
