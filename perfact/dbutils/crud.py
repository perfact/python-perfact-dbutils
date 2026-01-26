from __future__ import annotations
from psycopg2 import sql
from typing import Optional, Any
from collections.abc import Iterable, Mapping
from .conn import Executor
from typing import TypedDict


class Conditions(TypedDict):
    """Dictionary structure for passing conditions to crud functions"""
    stmt: str
    """The statement should contain the sql snippet which will be put into the
    where statement of the query. Actual values must not be put into the
    statement. Use placeholders like this for values: %(varname)s. Pass the
    actual value through the payload param.
    """
    payload: Mapping[str, Any]
    """Mapping of placeholders that were used in the statement to actual
    values."""


def _create_query(
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


def create(
        conn: Executor, table: str,
        payload: Optional[Mapping[str, Any]] = None
) -> Optional[Mapping[str, Any]]:
    """
    Create a new entry in the specified table with the given payload.

    :param conn: Connection object to database where the
        entry should be created
    :type conn: Executor
    :param table: Name of table in the database
    :type table: str
    :param payload: Mapping of full column names and values
    :type payload: Optional[Mapping[str, Any]]
    :return: The content of the created entry
    :rtype: Mapping[str, Any]
    """
    if payload is None:
        payload = {}
    columns = payload.keys()
    query = _create_query(table=table, columns=columns)
    res = conn.execute(query=query, **payload)
    if not res.tuples:
        return None
    return list(res.dicts())[0]


def _update_query(
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
    conn.execute(_update_query(table, ident, payload, auditmode), **args)


def _delete_query(
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
    conn.execute(_delete_query(table, ident), **ident)


def _read_query(
        table: str,
        columns: list[str] = [],
        ident: Mapping[str, Any] = {},
        where: Optional[Conditions] = None,
        orderby: Optional[list[tuple[str, str] | str]] = None,
        limit: Optional[int] = None,
        for_update: bool = False,
) -> sql.Composed:
    """
    Generate an SQL select statement based on the given params.

    :param table: Name of the table
    :type table: str

    :param columns: List of column names that should be selected
    :type column: list[str]

    :param ident: A mapping of column names to values for identifying the rows
        that should be selected
    :type ident: Mapping[str, Any]

    :param where: Dict containing an sql where expression and a payload if
        necessary. The dict has the following fields: stmt, payload. Optional.
        Defaults to None.
    :type where: Conditions

    :param orderby: List of order by expression. Each row can either be a
        string (colname) or a tuple of two strings (colname, (asc|desc)).
    :type orderby: list[tuple[str, str] | str]

    :param limit: Limit for the query
    :type limit: int

    :param for_update: If true, the selected rows will be locked for update
    :type for_update: bool

    :returns: Returns the generated select statement
    :rtype: sql.Composed
    """

    # Prepare replacements
    ident_conditions_sql: sql.Composable = sql.SQL('true')
    if ident:
        ident_conditions = _generate_ident_conditions(ident, prefix='ident')
        ident_conditions_sql = sql.SQL(' and ').join(ident_conditions)

    columns_sql = (
        sql.SQL(', ').join(map(sql.Identifier, columns))
        if columns else sql.SQL('*')
    )
    conditions_sql = sql.SQL(where['stmt']) if where else sql.SQL('true')
    orderby_sql = _build_order_by(orderby=orderby) if orderby else sql.SQL('')
    limit_sql = sql.SQL('limit %(limit)s') if limit else sql.SQL('')
    forupdate_sql = sql.SQL('for update') if for_update else sql.SQL('')

    return sql.SQL(
        'select {columns} from {table} '
        'where {ident_conditions} and ({conditions}) '
        '{orderby} '
        '{limit} '
        '{forupdate}'
    ).format(
        table=sql.Identifier(table),
        columns=columns_sql,
        ident_conditions=ident_conditions_sql,
        conditions=conditions_sql,
        orderby=orderby_sql,
        limit=limit_sql,
        forupdate=forupdate_sql,
    )


def read(
        conn: Executor,
        table: str,
        columns: list[str] = [],
        ident: Mapping[str, Any] = {},
        where: Optional[Conditions] = None,
        orderby: Optional[list[tuple[str, str] | str]] = None,
        limit: Optional[int] = None,
        for_update: bool = False,
) -> list[Mapping[str, Any]]:
    """
    Execute a read operation on the given table.

    :param conn: The database connection to use for executing the read
        operation
    :type conn: Executor

    :param table: Name of the table
    :type table: str

    :param columns: List of column names that should be selected
    :type column: list[str]

    :param ident: A mapping of column names to values for identifying the rows
        that should be selected
    :type ident: Mapping[str, Any]

    :param where: Dict containing an sql where expression and a payload if
        necessary. The dict has the following fields: stmt, payload. Optional.
        Defaults to None.
    :type where: Conditions

    :param orderby: List of order by expression. Each row can either be a
        string (colname) or a tuple of two strings (colname, (asc|desc)).
    :type orderby: list[tuple[str, str] | str]

    :param limit: Limit for the query
    :type limit: int

    :param for_update: If true, the selected rows will be locked for update
    :type for_update: bool

    :returns: Returns a list of dicts containing the selected rows
    :rtype: list[Mapping[str, Any]]
    """
    args = {}
    if ident:
        args = {f'ident_{key}': value for key, value in ident.items()}
    if where and where.get('payload'):
        args.update(where['payload'])

    if limit:
        args['limit'] = limit

    res = conn.execute(
        _read_query(table, columns, ident, where, orderby, limit, for_update),
        **args
    )
    if not res.tuples:
        return []
    return list(res.dicts())


def _build_order_by(
    orderby: list[tuple[str, str] | str]
) -> sql.Composed:
    """
    Generate an ORDER BY statement for sql queries from a list of order by
    expressions.

    :param orderby: List of order by expression. Each row can either be a
        string (colname) or a tuple of two strings (colname, (asc|desc)).
    :type orderby: list[tuple[str, str] | str]

    :returns: Returns an sql order by expression
    :rtype: sql.Composed
    """

    allowed_sort_direction = {
        'asc': sql.SQL('asc'),
        'desc': sql.SQL('desc'),
    }
    order_by_list: list[sql.Composed | sql.Identifier] = []

    for orderby_expr in orderby:
        # In case we have string
        if isinstance(orderby_expr, str):
            order_by_list.append(sql.Identifier(orderby_expr))
            continue
        # For tuple make sure we only pass desc or asc as sort direction
        if len(orderby_expr) != 2:
            raise ValueError(
                "Invalid length of orderby tuple. Expected len = 2. "
                f"Got {len(orderby_expr)}"
            )
        column = orderby_expr[0]
        direction = orderby_expr[1].lower()
        try:
            direction_sql = allowed_sort_direction[direction]
        except KeyError:
            raise ValueError(
                f"Invalid ORDER BY direction: {direction}"
            )

        order_by_list.append(
            sql.SQL('{column} {direction}').format(
                column=sql.Identifier(column),
                direction=direction_sql,
            )
        )

    return sql.SQL('order by {order_by_expr}').format(
        order_by_expr=sql.SQL(', ').join(order_by_list)
    )


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
