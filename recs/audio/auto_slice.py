import typing as t

__all__ = ('auto_slice',)


def auto_slice(channels: int) -> dict[str, slice]:
    def slicer() -> t.Iterator[tuple[str, slice]]:
        # Display channnels start at channel 1, not 0
        for i in range(0, channels - 1, 2):
            yield f'{i + 1}-{i + 2}', slice(i, i + 2)
        if channels % 2:
            yield f'{channels}', slice(channels - 1, channels)

    return dict(slicer())
