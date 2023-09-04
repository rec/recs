from recs.audio import mux


def test_auto_slice():
    assert mux.auto_slice(0) == {}
    assert mux.auto_slice(1) == {'1': slice(0, 1)}
    assert mux.auto_slice(2) == {'1-2': slice(0, 2)}
    assert mux.auto_slice(3) == {'1-2': slice(0, 2), '3': slice(2, 3)}
    assert mux.auto_slice(4) == {'1-2': slice(0, 2), '3-4': slice(2, 4)}
