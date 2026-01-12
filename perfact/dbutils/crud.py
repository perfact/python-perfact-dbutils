from __future__ import annotations
from psycopg import sql
from typing import Optional, Any
from collections.abc import Iterable, Mapping
from .conn import Executor


def insert_query(
        table: str,
        columns: Optional[Iterable[str]] = None
) -> sql.Composed:
    """Generate an SQL Insert statement based on the given table and columns

    :param table: Tablename in the database
    :type table: str
    :param columns: List of full column names to insert values for
    :type columns: Optional[Sequence[str]]
    :return: The SQL insert statement
    :rtype: sql.Composed
    """
    if columns:
        return sql.SQL(
            "insert into {table} ({columns}) values ({fields}) returning *",
        ).format(
            table=sql.Identifier(table),
            columns=sql.SQL(', ').join(map(sql.Identifier, columns)),
            fields=sql.SQL(', ').join(map(sql.Placeholder, columns))
        )
    else:
        return sql.SQL(
            "insert into {table} default values returning *").format(
            table=sql.Identifier(table)
        )


def insert(
        conn: Executor, table: str,
        payload: Optional[Mapping[str, Any]] = None
) -> Optional[Mapping[str, Any]]:
    """
    Insert a new entry into the specified table with the given payload.

    :param conn: Connection object to database where the
        entry should be inserted
    :type conn: Executor
    :param table: Name of table in the database
    :type table: str
    :param payload: Mapping of full column names and values
    :type payload: Optional[Mapping[str, Any]]
    :return: The content of the inserted entry
    :rtype: Mapping[str, Any]
    """
    if payload is None:
        payload = {}
    columns = payload.keys()
    query = insert_query(table=table, columns=columns)
    res = conn.execute(query=query, **payload)
    if not res.tuples:
        return None
    return list(res.dicts())[0]


def update_query(
        table: str,
        ident: Mapping[str, Any],
        payload: Mapping[str, Any],
        auditmode: bool = True
) -> sql.Composed:
    """
    Generate an SQL Update statement based on the given table, ident, and
        payload

    :param table: The name of the table to update
    :type table: str
    :param ident: Mapping of full column name and value for the row to update
    :type ident: Mapping[str, Any]
    :param payload: Mapping of full column names and new values to set
    :type payload: Mapping[str, Any]
    :param auditmode: Flag to enable or disable audit mode, which sets
        author and modtime columns if they are not already included in the
        payload
    :type auditmode: bool
    :return: The SQL update statement
    :rtype: sql.Composed
    """
    ident_conditions = _generate_ident_conditions(ident, prefix='ident')

    update_conditions: list[sql.Composed | sql.SQL] = [sql.SQL('false')]
    for column in payload.keys():
        update_conditions.append(
            sql.SQL('{column} is distinct from {value}').format(
                column=sql.Identifier(column),
                value=sql.Placeholder(column)
            )
        )

    # if auditmode
    columns = list(payload.keys())
    values: list[sql.SQL | sql.Composable] = list(
        map(sql.Placeholder, columns))
    if auditmode and f'{table}_author' not in columns:
        columns.append(f'{table}_author')
        values.append(sql.SQL('db_username()'))
    if auditmode and f'{table}_modtime' not in columns:
        columns.append(f'{table}_modtime')
        values.append(sql.SQL('now()'))

    return sql.SQL(
        'update {table} '
        'set ({columns}) '
        '= row({values}) '
        'where {ident_conditions} and ({update_conditions})'
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(', ').join(map(sql.Identifier, columns)),
        values=sql.SQL(', ').join(values),
        ident_conditions=sql.SQL(' and ').join(ident_conditions),
        update_conditions=sql.SQL(' or ').join(update_conditions),
    )


def update(
        conn: Executor,
        table: str,
        ident: Mapping[str, Any],
        payload: Mapping[str, Any],
        auditmode: bool = True,
) -> None:
    """
    Update a row in the specified table based on the provided ident
        and payload.

    :param conn: Database connection to use for the update operation
    :type conn: Executor
    :param table: The name of the table to update
    :type table: str
    :param ident: Mapping of full column name and value for the row to update
    :type ident: Mapping[str, Any]
    :param payload: Mapping of full column names and new values to set
    :type payload: Mapping[str, Any]
    :param auditmode: Flag to enable or disable audit mode which sets
        author and modtime columns if they are not already included in the
        payload
    :type auditmode: bool
    """
    args = {f'ident_{k}': v for k, v in ident.items()}
    args.update(payload)
    conn.execute(update_query(table, ident, payload, auditmode), **args)


def delete_query(
        table: str,
        ident: Mapping[str, Any]
) -> sql.Composed:
    """
    Generate an SQL Delete statement based on the given table and ident

    :param table: The name of the table to delete from
    :type table: str
    :param ident: A mapping of column names to values for identifying the
        row(s) to delete
    :type ident: Mapping[str, Any]
    :return: The SQL delete statement
    :rtype: sql.Composed
    """
    ident_conditions = _generate_ident_conditions(ident)

    return sql.SQL(
        'delete from {table} '
        'where {ident_conditions}'
    ).format(
        table=sql.Identifier(table),
        ident_conditions=sql.SQL(' and ').join(ident_conditions),
    )


def delete(
        conn: Executor,
        table: str,
        ident: Mapping[str, Any]
) -> None:
    """
    Execute a delete operation on the specified table for rows matching the
    provided ident.

    :param conn: The database connection to use for executing the delete
        operation
    :type conn: Executor
    :param table: The name of the table to delete from
    :type table: str
    :param ident: A mapping of column names to values for identifying the
        row(s) to delete
    :type ident: Mapping[str, Any]
    """
    conn.execute(delete_query(table, ident), **ident)


def _generate_ident_conditions(
        ident: Mapping[str, Any],
        prefix: Optional[str] = None
) -> list[sql.SQL | sql.Composed]:
    """
    Generate SQL conditions for identifying rows based on the given ident

    :param ident: A mapping of column names to values for identifying rows
    :type ident: Mapping[str, Any]
    :param prefix: An optional prefix to add to the placeholder names
    :type prefix: Optional[str]
    :return: A list of SQL conditions for the ident
    :rtype: list[SQL]
    """
    ident_conditions: list[sql.SQL | sql.Composed] = [sql.SQL('true')]
    for column, value in ident.items():
        placeholder = f'{prefix}_{column}' if prefix else column
        if value is None:
            ident_conditions.append(sql.SQL('{column} is null').format(
                column=sql.Identifier(column)
            ))
        else:
            ident_conditions.append(sql.SQL('{column} = {value}').format(
                column=sql.Identifier(column),
                value=sql.Placeholder(placeholder)
            ))

    return ident_conditions
