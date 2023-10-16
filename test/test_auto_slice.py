from recs.audio.auto_slice import auto_slice


def test_auto_slice():
    assert auto_slice(0) == {}
    assert auto_slice(1) == {'1': slice(0, 1)}
    assert auto_slice(2) == {'1-2': slice(0, 2)}
    assert auto_slice(3) == {'1-2': slice(0, 2), '3': slice(2, 3)}
    assert auto_slice(4) == {'1-2': slice(0, 2), '3-4': slice(2, 4)}
