from math import fsum

import numpy as np
from ufor.arrangement import ControlClip
from ufor.automation import AutomationScore, Interpolation, TimelineCurve, check_value
from ufor.modulation import Operation


def gain_values(
    automation: tuple[ControlClip, AutomationScore] | None,
    declared: float,
    start: int,
    frames: int,
) -> np.ndarray:
    if automation is None:
        return np.full(frames, declared, dtype=np.float32)
    clip, score = automation
    values = np.full(frames, declared, dtype=np.float32)
    first = max(start, clip.timeline_start)
    last = min(
        start + frames, clip.timeline_start + clip.source_end - clip.source_start
    )
    if first >= last:
        return values
    check_value(score.body.quantity, declared)
    source_start = clip.source_start + first - clip.timeline_start
    base = np.full(last - first, declared, dtype=np.float64)
    multipliers = np.ones(last - first, dtype=np.float64)
    additions: list[np.ndarray] = []
    for curve in sorted(score.body.curves, key=lambda c: c.name):
        if curve.operation is None:
            _apply_curve(base, curve, source_start)
        elif curve.operation == Operation.add:
            contribution = np.zeros(last - first, dtype=np.float64)
            _apply_curve(contribution, curve, source_start)
            additions.append(contribution)
        else:
            contribution = np.ones(last - first, dtype=np.float64)
            _apply_curve(contribution, curve, source_start)
            multipliers *= contribution
    if len(additions) == 1:
        base += additions[0]
    elif additions:
        # uFor uses fsum, not ordinary summation. Retain cancellation accuracy
        # while moving the expensive curve searches and interpolation out of Python.
        base += np.fromiter(
            (fsum(v) for v in zip(*additions, strict=True)), dtype=np.float64
        )
    base *= multipliers
    if not np.isfinite(base).all():
        raise ValueError('control values must be finite')
    if (base < 0).any():
        raise ValueError('gain must be nonnegative')
    values[first - start : last - start] = base
    return values


def _apply_curve(values: np.ndarray, curve: TimelineCurve, start: int) -> None:
    end = start + len(values)
    if end <= curve.at:
        return
    value = curve.initial
    at = curve.at
    for segment in curve.segments:
        duration = int(segment.duration)
        if duration != segment.duration:
            raise ValueError('automation segment duration must be an integer tick')
        next_at = at + duration
        left, right = max(start, at), min(end, next_at)
        if left >= right:
            at = next_at
            value = segment.to
            continue
        selected = slice(left - start, right - start)
        if curve.interpolation == Interpolation.hold:
            values[selected] = value
        else:
            progress = np.arange(left - at, right - at, dtype=np.float64) / duration
            if curve.interpolation == Interpolation.equal_power:
                values[selected] = (
                    (1 - progress) * float(value) ** 2
                    + progress * float(segment.to) ** 2
                ) ** 0.5
            else:
                values[selected] = (1 - progress) * float(value) + progress * float(
                    segment.to
                )
        at = next_at
        value = segment.to
    if end > at:
        values[max(0, at - start) :] = value
