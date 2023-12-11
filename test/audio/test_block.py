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


def test_asfloat1():
    b = Block(np.array([[1, 2], [3, 4], [5, 6]], dtype='float32'))
    assert b.is_float
    assert b.asfloat is b


def test_asfloat2():
    i = 0x4000
    b = Block(np.array([[i, i], [0, 0], [-i, -i]], dtype='int16'))
    assert not b.is_float
    assert b.asfloat is not b

    expected = Block(np.array([[0.5, 0.5], [0, 0], [-0.5, -0.5]], dtype='float32'))
    actual = b.asfloat.block
    assert np.allclose(actual, expected.block)


def test_rms1():
    b = Block(np.array([[0.5, 0.5], [0, 0], [-0.5, -0.5]], dtype='float32'))
    level = 1 / 6**0.5
    assert np.allclose(b.rms, [level, level])


def test_rms2():
    i = 0x4000
    b = Block(np.array([[i, i], [0, 0], [-i, -i]], dtype='int16'))
    print(b, b.asfloat)
    level = 1 / 6**0.5
    assert np.allclose(b.rms, [level, level])
