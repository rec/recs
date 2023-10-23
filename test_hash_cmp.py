import dataclasses as dc
from functools import partial, cached_property
import typing as t
import pytest


from recs.audio.hash_cmp import HashCmp


class Cmp(HashCmp):
    def __init__(self, i: int):
        self._key = -i



def test_hash_cmp():
    assert Cmp(1) < Cmp(-2)
    assert Cmp(1) == Cmp(1)
    assert Cmp(1) != 'hello'


def test_error1():
    with pytest.raises(TypeError) as e:
        Cmp(1) < 3
    assert e.value.args == ("'<' not supported between instances of 'Cmp' and 'int'",)
