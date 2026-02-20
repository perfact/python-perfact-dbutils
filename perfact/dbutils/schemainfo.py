from __future__ import annotations
from .conn import Executor
from collections.abc import Mapping
from typing import Any


def get_columns(
        conn: Executor,
        table: str,
        full_colname: bool = True
) -> list[str]:
    """Get the column names for a given table.

    :param conn: Connection object to database where the table is stored
    :param table: Name of the table in the database
    :param full_colname: If true, the full column names will be selected.
        Otherwise the table prefix will be removed from the column names.
    :return: Returns a list of column names
    """
    query = """--sql
        select
          array_agg(
            column_name::text
          ) as columns
        from information_schema.columns
        where table_schema not in ( 'pg_catalog', 'information_schema', 'hist')
          and table_name = %(table)s
    """
    payload: Mapping[str, Any] = {'table': table}
    res = conn.execute(query=query, **payload)
    columns = next(iter(res.rows())).columns
    if not columns:
        columns = []
    if not full_colname:
        columns = [col.removeprefix(f"{table}_") for col in columns]
    return list(columns)
