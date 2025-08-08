import json

import pytest

from recs.base import RecsError
from recs.base.types import Format, SdType, Subtype
from recs.cfg import Cfg, run_cli


def test_list_types(capsys):
    run_cli.run_cli(Cfg(list_types=True))
    data = capsys.readouterr().out
    json.loads(data)


def test_error_incompatible():
    with pytest.raises(RecsError) as e:
        Cfg(formats=['flac'], subtype='float')
    assert e.value.args == ('flac and float are incompatible',)


def test_missing_subtype(capsys):
    r = Cfg(formats=[Format._default], sdtype=SdType.int16)
    assert r.subtype == Subtype.pcm_16


def test_error_subtype():
    match = "Can't get subtype for formats=mp3, sdtype=float32"
    with pytest.warns(UserWarning, match=match):
        Cfg(formats=[Format.mp3], sdtype=SdType.float32)


def test_default_dtype1():
    assert Cfg().sdtype == 'float32'


def test_default_dtype2():
    r = Cfg(formats=[Format.wav], subtype=Subtype.pcm_32)
    assert r.sdtype == SdType.int32


def test_default_subtype():
    r = Cfg(formats=[Format.wav], sdtype=SdType.int32)
    assert r.subtype == Subtype.pcm_32
