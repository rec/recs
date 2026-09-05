import numpy as np

from recs.edit.schema import AutomationSpec, Interpolation


def gain_values(
    automation: AutomationSpec | None,
    declared: float,
    start: int,
    frames: int,
) -> np.ndarray:
    positions = np.arange(start, start + frames)
    if automation is None:
        return np.full(frames, declared)
    points = automation.points
    result = np.full(frames, declared)
    for index, point in enumerate(points):
        next_point = points[index + 1] if index + 1 < len(points) else None
        selected = positions >= point.frame
        if next_point is not None:
            selected &= positions < next_point.frame
        if not selected.any():
            continue
        if next_point is None or automation.interpolation == Interpolation.hold:
            result[selected] = point.value
            continue
        fraction = (positions[selected] - point.frame) / (
            next_point.frame - point.frame
        )
        if automation.interpolation == Interpolation.equal_power:
            result[selected] = np.sqrt(
                (1 - fraction) * point.value**2 + fraction * next_point.value**2
            )
        else:
            result[selected] = point.value + fraction * (next_point.value - point.value)
    return result
