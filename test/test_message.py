from recs.base.message import ChannelMessage as CM


def test_message():
    assert CM() - CM() == CM()
    assert CM() + CM() == CM()

    a, b, c = CM(1, 2, False, 10), CM(10, 15, True, 2.5), CM(11, 17, True, 12.5)
    assert a + b == c
    assert c - a == b
