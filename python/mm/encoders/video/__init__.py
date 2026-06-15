from __future__ import annotations


def uniform_timestamps(duration: float, fps: float) -> list[float]:
    """Generate uniformly spaced timestamps at *fps* from 0 to *duration*."""
    interval: float = 1.0 / fps
    timestamps: list[float] = []
    t: float = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval
    return timestamps


def uniform_timestamps_range(start: float, end: float, count: int) -> list[float]:
    """Generate *count* uniformly spaced timestamps between *start* and *end*."""
    if count <= 1:
        return [start]
    step: float = (end - start) / count
    return [start + i * step for i in range(count)]
