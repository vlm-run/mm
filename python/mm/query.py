"""SQLite-based SQL queries against Arrow tables"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyarrow import Table


def query_arrow_table(table: Table, sql: str, table_name: str = "files") -> Table:
    """Run a SQL query against a PyArrow table using an in-memory SQLite DB."""
    from pyarrow import array, table, types
    from pyarrow import string as pa_string

    db = sqlite3.connect(":memory:")
    col_names = table.column_names

    # Create table with inferred types
    col_defs = []
    for field in table.schema:
        col_defs.append(f'"{field.name}" {_arrow_to_sqlite_type(field.type)}')
    db.execute(f"CREATE TABLE {table_name} ({', '.join(col_defs)})")

    # Batch insert — convert columns to Python lists once
    n = table.num_rows
    if n > 0:
        col_lists = [table.column(c).to_pylist() for c in col_names]
        # Convert booleans and timestamps to SQLite-compatible types
        for ci, field in enumerate(table.schema):
            if types.is_boolean(field.type):
                col_lists[ci] = [int(v) if v is not None else None for v in col_lists[ci]]
            elif types.is_timestamp(field.type):
                col_lists[ci] = [
                    int(v.timestamp() * 1_000_000) if v is not None else None for v in col_lists[ci]
                ]
        rows = [tuple(col_lists[ci][i] for ci in range(len(col_names))) for i in range(n)]
        placeholders = ", ".join("?" * len(col_names))
        db.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)

    # Query
    cursor = db.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    result_rows = cursor.fetchall()
    db.close()

    # Convert back to Arrow using per-column lists (faster than row-by-row)
    if not result_rows:
        return table({col: array([], type=pa_string()) for col in columns})
    col_data = {col: [row[ci] for row in result_rows] for ci, col in enumerate(columns)}
    return table(col_data)


def _arrow_to_sqlite_type(arrow_type) -> str:
    from pyarrow import types

    if types.is_integer(arrow_type) or types.is_boolean(arrow_type):
        return "INTEGER"
    if types.is_floating(arrow_type):
        return "REAL"
    if types.is_timestamp(arrow_type):
        return "INTEGER"
    return "TEXT"
