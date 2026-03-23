from collections.abc import Mapping
from typing import Any, Optional

from psycopg2 import sql

from .api import SelfilterGenerator
from .conn import Executor
from .crud import _generate_ident_conditions


def _build_lookups(columns: list[str]) -> Mapping[str, sql.Composed | None]:
    """Build lookups for all id columns in the given list. Returns a dictionary
    containing the lookup_columns and lookup_joins (left joins) each as
    sql.Composed.

    :param columns: List of columns
    :return: Returns a dictionary containing the lookup_columns and
        lookup_joins, each with keys of the same name.
    """
    id_cols = [column for column in columns if column.endswith("_id")]
    selviews = []
    lookup_columns = []
    for id_col in id_cols:
        col_parts = id_col.split("_")
        sel_name = None
        if len(col_parts) <= 3:
            # Usual pattern: table_id or parenttable_table_id
            sel_name = f"{col_parts[-2]}_sel"
        else:
            # Prefix pattern. We expect 4 parts:
            # parenttable_prefix_table_id
            sel_name = f"{col_parts[-3]}_{col_parts[-2]}_sel"
        selview_unique_name = f"{id_col}_sel"
        selviews.append(
            sql.SQL(
                """--sql
                left
                join {selview} as {selview_unique_name}
                  on {selview_unique_name}.id = {idcol}
                """
            ).format(
                selview=sql.Identifier(sel_name),
                selview_unique_name=sql.Identifier(selview_unique_name),
                idcol=sql.Identifier(id_col),
            )
        )
        lookup_columns.append(
            sql.SQL("{}.name as {}").format(
                sql.Identifier(selview_unique_name),
                sql.Identifier(f"lookup_{id_col}"),
            )
        )

    return {
        "lookup_joins": sql.SQL("\n").join(selviews) if selviews else None,
        "lookup_columns": (
            sql.SQL(",\n").join(lookup_columns) if lookup_columns else None
        ),
    }


def _load_records_query(
    table: str,
    columns: list[str],
    selfilter_generator: Optional[SelfilterGenerator] = None,
    add_lookups: Optional[bool] = True,
    ident: Optional[Mapping[str, Any]] = None,
    alias: Optional[Mapping[str, str]] = None,
    joins: Optional[str] = None,
    where: Optional[str] = None,
    orderby: Optional[str] = None,
    limit: Optional[int] = None,
) -> sql.Composed:
    """
    Generate a query to load records based on the given config.

    :param table: Name of the table to fetch data from
    :param columns: List of columns that will be selected. Can not be empty.
    :param selfilter_generator: Function that will generate the selfilter
        for the given table. If not given, the selfilter will not be included
        in the query.
    :param add_lookups: Add lookups for all id columns
    :param ident: A mapping of column names to values for identifying the rows
        that should be selected
    :param alias: Mapping of alias names to the expression for the alias column
    :param joins: SQL expression containing the joins. Placeholders must be
        used instead of actual values.
    :param where: SQL expression containing additonal conditions for the where
        statement. Placeholders must be used instead of actual values.
    :param orderby: SQL expression containing the orderby (without the actual
        order by keyword). Placeholders must be used instead of actual values.
    :param limit: Limit for the query

    :returns: Returns the generated query to select the desired records.
    """
    # Build columns sql
    if not columns:
        raise ValueError("No columns specified")
    column_list: list[sql.Identifier | sql.Composed] = [
        sql.Identifier(column) for column in columns
    ]
    alias = alias or {}
    for alias_name in alias:
        column_list.append(
            sql.SQL("{} as {}").format(
                sql.SQL(alias[alias_name]), sql.Identifier(alias_name)
            )
        )
    column_sql = sql.SQL(",\n").join(column_list)

    # Build columns and joins for lookup. Always use left joins for lookups
    lookup_joins_sql: sql.Composed | sql.SQL = sql.SQL("")
    lookup_columns_sql: sql.Composed | sql.SQL = sql.SQL("")
    if add_lookups:
        if alias:
            all_colnames = columns + list(alias.keys())
        else:
            all_colnames = columns
        lookups = _build_lookups(columns=all_colnames)
        if lookups["lookup_columns"] and lookups["lookup_joins"]:
            lookup_columns_sql = sql.SQL(", {}").format(
                lookups["lookup_columns"],
            )
            lookup_joins_sql = lookups["lookup_joins"]

    ident_conditions_sql: sql.Composable = sql.SQL("true")
    if ident:
        ident_conditions = _generate_ident_conditions(ident, prefix="ident")
        ident_conditions_sql = sql.SQL(" and ").join(ident_conditions)

    # Collect selfilter
    selfilter_sql = sql.SQL("true")
    if selfilter_generator:
        selfilter = selfilter_generator(table=table, column=f"{table}_id")
        selfilter_sql = sql.SQL(selfilter) if selfilter else sql.SQL("true")

    # Prepare other sql expressions
    limit_sql = sql.SQL("limit %(limit)s") if limit else sql.SQL("")
    join_sql = sql.SQL(joins) if joins else sql.SQL("")
    orderby_sql = sql.SQL(f"order by {orderby}") if orderby else sql.SQL("")
    conditions_sql = sql.SQL(where) if where else sql.SQL("true")

    query = sql.SQL("""--sql
        select
          *
          {lookup_columns}
        from (
          select
            {columns}
          from {table}
          {joins}
          where {ident_conditions} and {selfilter} and ({conditions})
          {orderby}
          {limit}
        ) as data
        {lookup_joins}
    """).format(
        lookup_columns=lookup_columns_sql,
        columns=column_sql,
        table=sql.Identifier(table),
        joins=join_sql,
        ident_conditions=ident_conditions_sql,
        selfilter=selfilter_sql,
        conditions=conditions_sql,
        orderby=orderby_sql,
        limit=limit_sql,
        lookup_joins=lookup_joins_sql,
    )
    return query


def load_records(
    conn: Executor,
    table: str,
    columns: list[str],
    selfilter_generator: Optional[SelfilterGenerator] = None,
    add_lookups: Optional[bool] = True,
    ident: Optional[Mapping[str, Any]] = None,
    alias: Optional[Mapping[str, str]] = None,
    joins: Optional[str] = None,
    where: Optional[str] = None,
    orderby: Optional[str] = None,
    limit: Optional[int] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> list[Mapping[str, Any]]:
    """
    Generate a query to load records based on the given config. Filters records
    always with the selfilter.

    :param conn: DB connector
    :param table: Name of the table to fetch data from
    :param columns: List of columns that will be selected. Can not be empty.
    :param selfilter_generator: Function that will generate the selfilter
        for the given table. If not given, the selfilter will not be included
        in the query.
    :param add_lookups: Add lookups for all id columns
    :param ident: A mapping of column names to values for identifying the rows
        that should be selected
    :param alias: Mapping of alias names to the expression for the alias column
    :param joins: SQL expression containing the joins. Placeholders must be
        used instead of actual values.
    :param where: SQL expression containing additonal conditions for the where
        statement. Placeholders must be used instead of actual values.
    :param orderby: SQL expression containing the orderby (without the actual
        order by keyword). Placeholders must be used instead of actual values.
    :param limit: Limit for the query
    :param payload: Mapping of the placeholders used in the joins, where and
        orderby expressions to actual values.

    :returns: Returns the selected rows as a list of dicts.

    .. code-block:: python

        from perfact.dbutils.genericloader import load_records

        rows = load_records(
            conn=conn,
            table='testlct',
            columns=[
                'testlct_id',
                'testlc_name',
            ],
            add_lookups=True,
            alias={
                'myalias': '1 < 2',
            },
            selfilter_generator=ctx.selfilter_generator,
            orderby='testlct_id desc, testlc_id = %(testlc_id)s desc',
            where='testlc_id = %(testlc_id)s',
            joins=(
                'join testlc on testlc_id = %(testlc_id)s'
            ),
            payload={'testlc_id': 3},
        )
        if rows:
            testlct_id = rows[0]['testlct_id]
    """
    args = {}
    if ident:
        args = {f"ident_{key}": value for key, value in ident.items()}
    if payload:
        args.update(payload)

    if limit:
        args["limit"] = limit

    res = conn.execute(
        _load_records_query(
            table=table,
            columns=columns,
            selfilter_generator=selfilter_generator,
            add_lookups=add_lookups,
            alias=alias,
            joins=joins,
            ident=ident,
            where=where,
            orderby=orderby,
            limit=limit,
        ),
        **args,
    )
    if not res.tuples:
        return []
    return list(res.dicts())
