import json

import pytest

from recs.audio.file_types import Format, SdType, Subtype
from recs.misc import RecsError
from recs.recs import Recs, run_recs


def test_list_subtypes(capsys, set_recs):
    set_recs(list_subtypes=True)
    run_recs()

    data = capsys.readouterr().out
    json.loads(data)


def test_error_incompatible():
    with pytest.raises(RecsError) as e:
        Recs(format='flac', subtype='float')
    assert e.value.args == ('flac and float are incompatible',)


def test_error_subdirectory1():
    with pytest.raises(RecsError) as e:
        Recs(subdirectory=['date', 'time', 'place'])
    assert e.value.args == ("Bad arguments to --subdirectory: ['date', 'place']",)


def test_error_subdirectory2():
    with pytest.raises(RecsError) as e:
        Recs(subdirectory=['t', 'c', 'cha'])
    assert e.value.args == ('Duplicates in --subdirectory',)


def test_missing_subtype(capsys):
    r = Recs(format=Format.flac, sdtype=SdType.int16)
    assert r.subtype == Subtype.pcm_16


def test_error_subtype():
    match = "Can't get subtype for self.format=mp3, self.sdtype=float32"
    with pytest.warns(UserWarning, match=match):
        Recs(format=Format.mp3, sdtype=SdType.float32)


def test_default_dtype1():
    assert Recs().sdtype is None


def test_default_dtype2():
    r = Recs(format=Format.wav, subtype=Subtype.pcm_32)
    assert r.sdtype == SdType.int32


def test_default_subtype():
    r = Recs(format=Format.wav, sdtype=SdType.int32)
    assert r.subtype == Subtype.pcm_32
