import numpy as np
from ufor.arrangement import ControlClip
from ufor.automation import AutomationScore, evaluate


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
    positions = np.arange(start, start + frames)
    selected = (positions >= clip.timeline_start) & (
        positions < clip.timeline_start + clip.source_end - clip.source_start
    )
    source_ticks = clip.source_start + positions[selected] - clip.timeline_start
    values[selected] = [evaluate(score, int(tick), declared) for tick in source_ticks]
    return values
