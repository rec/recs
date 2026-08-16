from collections.abc import Callable
from importlib import import_module
from typing import cast

from recs.cfg.cfg import Cfg


def input_names() -> list[str]:
    mido = import_module('mido')
    get_input_names = cast(Callable[[], list[str]], vars(mido)['get_input_names'])
    return list(get_input_names())


def selected_inputs(cfg: Cfg, names: list[str] | None = None) -> list[str]:
    values = names if names is not None else input_names()
    selected = [
        name
        for name in values
        if _included(cfg.midi.midi_include, name)
        and not _excluded(cfg.midi.midi_exclude, name)
    ]
    return sorted(selected)


def _included(patterns: list[str], value: str) -> bool:
    return not patterns or any(value.startswith(pattern) for pattern in patterns)


def _excluded(patterns: list[str], value: str) -> bool:
    return any(value.startswith(pattern) for pattern in patterns)
