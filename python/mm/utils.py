from __future__ import annotations

import sys
import time as _time
from enum import Enum
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class BaseFormat(str, Enum):
    json = "json"
    tsv = "tsv"
    csv = "csv"


class Format(str, Enum):
    json = "json"
    tsv = "tsv"
    csv = "csv"
    dataset_jsonl = "dataset-jsonl"
    dataset_hf = "dataset-hf"


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


def benchmark_func(
    callback: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run callback and return (result, elapsed_ms)."""
    print(f"Benchmarking function: {callback.__name__}", file=sys.stderr)
    result, elapsed_ms = get_elapsed_ms(callback, *args, **kwargs)
    print(f"Execution time for {callback.__name__}: {elapsed_ms:.2f} ms", file=sys.stderr)

    return result


def batch_array(arr: list[T], x: int) -> list[list[T]]:
    if x <= 0:
        raise ValueError("x must be greater than 0")
    return [arr[i : i + x] for i in range(0, len(arr), x)]
