"""DuckDB integration for SQL queries against the index."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyarrow as pa


def query_arrow_table(table: pa.Table, sql: str, table_name: str = "files") -> pa.Table:
    """Run a SQL query against a PyArrow table using DuckDB."""
    import duckdb

    con = duckdb.connect()
    con.register(table_name, table)
    result = con.execute(sql).fetch_arrow_table()
    con.close()
    return result


def query_parquet(parquet_path: str, sql: str) -> pa.Table:
    """Run a SQL query against a Parquet file using DuckDB."""
    import duckdb

    con = duckdb.connect()
    escaped = parquet_path.replace("'", "''")
    full_sql = sql.replace("files", f"read_parquet('{escaped}')")
    result = con.execute(full_sql).fetch_arrow_table()
    con.close()
    return result
