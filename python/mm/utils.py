import time as _time
from typing import Callable, ParamSpec, TypeVar

from rich.text import Text

P = ParamSpec("P")
T = TypeVar("T")


def get_elapsed_ms(
    callback: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> tuple[T, float]:
    """Run callback and return (result, elapsed_ms)."""
    _t0 = _time.perf_counter()
    content = callback(*args, **kwargs)
    elapsed_ms = (_time.perf_counter() - _t0) * 1000

    return content, elapsed_ms


def inject_elapsed(subtitle: Text, elapsed_ms: float) -> Text:
    if elapsed_ms > 0:
        if elapsed_ms < 1000:
            subtitle.append(f"  {elapsed_ms:.0f}ms", style="bright_green")
        else:
            subtitle.append(f"  {elapsed_ms / 1000:.1f}s", style="bright_green")
    return subtitle
