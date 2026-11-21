# Adapted from fDisBull commit 9853c99952c2c0b77f2d9e33f99a05f0a242882b.
# Source: https://github.com/seeker-cyber-maker/fDisBull
# Original module: src/fdisbull/dos_launch_profile.py
"""Bounded DOS command tails for the standalone native transport.

CD descriptors require the separate disc-analysis pipeline and are deliberately
outside this DOSBox-only play slice. No host shell command is accepted.
"""
from copy import deepcopy
import re


def prepare_launch_options(arguments=None, cd_image=None):
    """Validate explicit unquoted ASCII tokens before an owned process starts."""
    if cd_image is not None:
        raise ValueError('CD launch profiles are not supported by standalone DotBox')
    explicit = arguments is not None
    if arguments is None:
        arguments = []
    if (not isinstance(arguments, list) or len(arguments) > 32 or any(
            not isinstance(argument, str) or re.fullmatch(
                r'[A-Za-z0-9_./:+,=@\\-]+', argument) is None
            for argument in arguments) or len(' '.join(arguments)) > 125):
        raise ValueError('DOS arguments require at most 32 unquoted ASCII tokens and a 125-byte joined tail')
    return {'format': 'dotbox-dos-launch-profile-1', 'explicit': explicit,
            'arguments': list(arguments), 'cd': None}


def bind_start(params, profile):
    """Copy session-start intent; preserve the native request and caller data."""
    if not isinstance(params, dict) or not isinstance(params.get('target'), dict):
        raise ValueError('Expected an explicit DOS session target')
    requested = params['target'].get('arguments', [])
    if requested not in ([], profile['arguments']):
        raise ValueError('Conflicting DOS launch arguments')
    if profile.get('cd') is not None:
        raise ValueError('CD launch profiles are not supported by standalone DotBox')
    result = deepcopy(params)
    result['target']['arguments'] = list(profile['arguments'])
    return result
