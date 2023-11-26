from recs.base.state import ChannelState

TIMESTAMP = 1_700_000_000


def cm(*a, **ka):
    return ChannelState(*a, **ka, timestamp=TIMESTAMP)


def test_message():
    assert cm() - cm() == cm()
    assert cm() + cm() == cm()

    a, b, c = cm(1, 2, False, 10), cm(10, 15, True, 2.5), cm(11, 17, True, 12.5)
    assert a + b == c
    assert c - a == b
