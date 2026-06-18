from recs.base.state import ChannelState

TIMESTAMP = 1_700_000_000


def cm(*a, **ka):
    fields = tuple(ChannelState.model_fields)
    values = dict(zip(fields, ('running', *a), strict=False))
    return ChannelState(**values, **ka, timestamp=TIMESTAMP)


def test_message():
    assert cm() - cm() == cm()
    assert cm() + cm() == cm()

    a = cm(1, 2, False, 0.5, -0.4, 10)
    b = cm(10, 15, True, 0.4, -0.6, 2.5)
    c = cm(11, 17, True, 0.5, -0.6, 12.5)
    assert a + b == c
    assert c - a == b.model_copy(update={'max_amp': 0.5})
