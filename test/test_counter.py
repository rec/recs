from recs import counter


def test_counter():
    c = counter.Counter()
    assert c.increment() == 1
    assert c.increment() == 2
    assert c.increment(0) == 2
    assert c.increment(3) == 5


def test_accumulator():
    a = counter.Accumulator()
    [a(i) for i in range(16)]

    assert a.count == 16
    assert a.mean() == 7.5
    assert a.variance() == 77.5
