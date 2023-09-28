from recs.ui import counter


def test_counter():
    c = counter.Counter()
    assert c() == 1
    assert c() == 2
    assert c(0) == 2
    assert c(3) == 5


def test_accumulator():
    a = counter.Accumulator()
    [a(i) for i in range(16)]

    assert a.count == 16
    assert a.mean() == 7.5
    assert a.variance() == 77.5
