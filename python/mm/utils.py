import time as _time
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def get_elapsed_ms(
    callback: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> tuple[T, float]:
    """Run callback and return (result, elapsed_ms)."""
    _t0 = _time.perf_counter()
    result = callback(*args, **kwargs)
    elapsed_ms = (_time.perf_counter() - _t0) * 1000

    return result, elapsed_ms


