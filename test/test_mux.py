import recs.util.slicer
from recs.audio import mux


def test_auto_slice():
    assert recs.util.slicer.auto_slice(0) == {}
    assert recs.util.slicer.auto_slice(1) == {'1': slice(0, 1)}
    assert recs.util.slicer.auto_slice(2) == {'1-2': slice(0, 2)}
    assert recs.util.slicer.auto_slice(3) == {'1-2': slice(0, 2), '3': slice(2, 3)}
    assert recs.util.slicer.auto_slice(4) == {'1-2': slice(0, 2), '3-4': slice(2, 4)}
