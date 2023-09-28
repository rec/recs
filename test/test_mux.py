import recs.audio.slicer


def test_auto_slice():
    assert recs.audio.slicer.auto_slice(0) == {}
    assert recs.audio.slicer.auto_slice(1) == {'1': slice(0, 1)}
    assert recs.audio.slicer.auto_slice(2) == {'1-2': slice(0, 2)}
    assert recs.audio.slicer.auto_slice(3) == {'1-2': slice(0, 2), '3': slice(2, 3)}
    assert recs.audio.slicer.auto_slice(4) == {'1-2': slice(0, 2), '3-4': slice(2, 4)}
