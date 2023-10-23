import numpy as np
import pytest

from recs.audio.block import Block


def test_block1():
    b = Block(np.array(range(3)))
    assert len(b) == 3
    assert b.channel_count == 1


def test_block2():
    b = Block(np.array([[1, 2], [3, 4], [5, 6]]))
    assert len(b) == 3
    assert b.channel_count == 2


def test_empty1():
    with pytest.raises(ValueError) as e:
        Block(np.array(()))
    assert e.value.args == ('Empty block',)


@pytest.mark.parametrize('empty', [0, (0,), (0, 3), (3, 0)])
def test_empty(empty):
    with pytest.raises(ValueError) as e:
        Block(np.empty(shape=empty))
    assert e.value.args == ('Empty block',)


def test_slice():
    source = Block(np.array([[1, 2], [3, 4], [5, 6]]))
    actual = source[0:2, :]
    expected = Block(np.array([[1, 2], [3, 4]]))
    assert np.allclose(actual.block, expected.block)
