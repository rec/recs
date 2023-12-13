from pathlib import Path


def test_clean_flac():
    for f in list(Path(__file__).parents[1].glob('*.flac')):
        f.unlink()
