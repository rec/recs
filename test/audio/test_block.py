from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.audio.block import Block


def test_block1():
    b = Block(block=np.array(range(3)))
    assert len(b) == 3
    assert b.channel_count == 1


def test_block2():
    b = Block(block=np.array([[1, 2], [3, 4], [5, 6]]))
    assert len(b) == 3
    assert b.channel_count == 2


def test_empty1():
    with pytest.raises(ValueError) as e:
        Block(block=np.array(()))
    assert 'Empty block' in str(e.value)


@pytest.mark.parametrize('empty', [0, (0,), (0, 3), (3, 0)])
def test_empty(empty):
    with pytest.raises(ValueError) as e:
        Block(block=np.empty(shape=empty))
    assert 'Empty block' in str(e.value)


def test_slice():
    source = Block(block=np.array([[1, 2], [3, 4], [5, 6]]))
    actual = source[0:2, :]
    expected = Block(block=np.array([[1, 2], [3, 4]]))
    assert np.allclose(actual.block, expected.block)


def test_asfloat1():
    b = Block(block=np.array([[1, 2], [3, 4], [5, 6]], dtype='float32'))
    assert b.is_float
    assert b.asfloat is b


def test_asfloat2():
    i = 0x4000
    b = Block(block=np.array([[i, i], [0, 0], [-i, -i]], dtype='int16'))
    assert not b.is_float
    assert b.asfloat is not b

    expected = Block(
        block=np.array([[0.5, 0.5], [0, 0], [-0.5, -0.5]], dtype='float32')
    )
    actual = b.asfloat.block
    assert np.allclose(actual, expected.block)


def test_rms1():
    b = Block(block=np.array([[0.5, 0.5], [0, 0], [-0.5, -0.5]], dtype='float32'))
    level = 1 / 6**0.5
    assert np.allclose(b.rms, [level, level])


def test_rms2():
    i = 0x4000
    b = Block(block=np.array([[i, i], [0, 0], [-i, -i]], dtype='int16'))
    print(b, b.asfloat)
    level = 1 / 6**0.5
    assert np.allclose(b.rms, [level, level])


@pytest.mark.parametrize('first', [True, False])
def test_rms_preserves_cached_integer_conversion(tmp_path: Path, first: bool) -> None:
    samples = np.tile(np.array([-16384, 0, 16384], dtype=np.int16), 16000)
    path = tmp_path / 'integer.wav'
    soundfile.write(path, samples, 48000, subtype='PCM_16')
    samples, rate = soundfile.read(path, dtype='int16', always_2d=True)
    block = Block(block=samples)
    if first:
        assert np.allclose(block.rms, np.sqrt(1 / 6))
    expected = samples.astype(np.float32) / 32768
    np.testing.assert_array_equal(block.asfloat.block, expected)
    assert np.allclose(block.rms, np.sqrt(1 / 6))
    np.testing.assert_array_equal(block.asfloat.block, expected)
    soundfile.write(
        tmp_path / 'converted.wav', block.asfloat.block, rate, subtype='FLOAT'
    )
