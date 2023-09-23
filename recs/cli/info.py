import typing as t

import dtyper

from .app import command


@command(help='Info')
def info(
    kind: t.Optional[str] = dtyper.Argument(None),
):
    import json

    import sounddevice as sd

    info = sd.query_devices(kind=kind)

    def accept(k):
        if 'channel' in k:
            return k.replace('max_', '')
        if 'sample' in k:
            return 'sample_rate'

    def to_entry(d):
        return d['name'], {j: v for k, v in d.items() if (j := accept(k))}

    info = dict(to_entry(d) for d in info)

    print(json.dumps(info, indent=2))
