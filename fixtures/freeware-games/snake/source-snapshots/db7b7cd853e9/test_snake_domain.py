"""The browser adapter enforces the recovered original's state preconditions."""
from copy import deepcopy

import pytest

from examples.recovery.snake_browser import plan
from examples.recovery.snake_model import make_program,initial_words,STATE
from fdisbull.udc_memory_shell import validate_plan,validate_arena
from fdisbull.udc_web_memory import execute_memory_uil


def fixture():
    program=make_program()
    p=plan(program,{str(k):[0,0,0] for k in (0,1,2,8,10,12,15)})
    validate_plan(p,program)
    words=execute_memory_uil(program,'reset',initial_words(bytes(2048)))['words']
    assert validate_arena(p,words)
    return p,words


@pytest.mark.parametrize('name',['score','key_events','mouse_events','last_tick','food_cell'])
def test_dos_word_fields_refuse_wider_carriers(name):
    p,words=fixture();words[STATE[name]]=0x10000
    with pytest.raises(ValueError):validate_arena(p,words)


@pytest.mark.parametrize('mutate',[
    lambda w:w.__setitem__(0,600),
    lambda w:w.__setitem__(1,w[0]),
    lambda w:w.__setitem__(1,300),
    lambda w:w.__setitem__(STATE['food_cell'],w[0]),
    lambda w:w.__setitem__(STATE['food_cell'],600),
])
def test_active_prefix_and_food_domain_are_admitted_explicitly(mutate):
    p,words=fixture();before=deepcopy(words);mutate(words)
    with pytest.raises(ValueError):validate_arena(p,words)
    assert validate_arena(p,before)


def test_terminal_food_sentinel_and_original_u16_wrap_domain_remain_admitted():
    p,words=fixture();words[STATE['game_status']]=2;words[STATE['food_cell']]=65535
    words[STATE['score']]=65535
    assert validate_arena(p,words)
