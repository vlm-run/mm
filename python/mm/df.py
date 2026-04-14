"""DataFrame conversion helpers -- first-class Pandas and Polars support."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl
    import pyarrow as pa


def arrow_to_polars(table: pa.Table) -> pl.DataFrame:
    """Convert PyArrow Table to Polars DataFrame (zero-copy)."""
    import polars

    result = polars.from_arrow(table)
    assert isinstance(result, polars.DataFrame)
    return result


def arrow_to_pandas(table: pa.Table) -> pd.DataFrame:
    """Convert PyArrow Table to Pandas DataFrame (zero-copy for numeric columns)."""
    return table.to_pandas()
