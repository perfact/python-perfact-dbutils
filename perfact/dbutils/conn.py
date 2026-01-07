class Namespace(object):
    """
    Convert a dict to a namespace, allowing access via a.b instead of a['b']
    """
    def __init__(self, data=None, **kw):
        if data:
            self.__dict__.update(data)
        self.__dict__.update(kw)


def _dicts(result):
    """
    Create generator from result that yields dicts
    """
    names = result.names
    for row in result.tuples:
        yield {key: value for key, value in zip(names, row)}


def _rows(result):
    """
    Create generator from result that yields namespaces
    """
    for row in _dicts(result):
        yield Namespace(**row)


def _prepare_result(names, rows):
    """
    Returns None if no names are given, otherwise a Namespace with "names" and
    "tuples" as well as generators "dicts()" and "rows()" yielding the results
    as dictionaries or namespaces.
    """
    if not names:
        return
    result = Namespace(names=tuple(names), tuples=rows)
    result.dicts = lambda: _dicts(result)
    result.rows = lambda: _rows(result)
    return result


class Connection:
    """
    Wrapper exposing a nice execute method.
    Is initialized with something that has an execute method like a Connection
    from psycopg.
    """
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, **args):
        """
        Execute given query. Returns a namespace with "names" and "tuples". If
        parameters are to be used, they should be included in the form of
        %(name)s in the query. The result also contains methods dicts() and
        rows() that provide generators for getting the results as dictionaries
        or namespaces.
        """
        rows = self.conn.execute(query, args)
        if not rows.description:
            return
        return _prepare_result(
            (col.name for col in rows.description),
            rows.fetchall(),
        )


class ZRDBConnectionWrapper:
    """
    Wrap a ZRDB.Connection into something with a matching execute method
    """
    def __init__(self, conn):
        self.conn = conn._v_database_connection

    def execute(self, query, **args):
        """
        Execute within a Zope transaction
        """
        if not isinstance(query, str):
            # We assume this is a ZSQLMethod
            query = query(src__=1)

        res = self.conn.query(query, query_data=args)
        # Now we have a tuple with the first element containing a list of
        # column descriptions and the second containing the list of results
        return _prepare_result((col['name'] for col in res[0]), res[1])


def wrap_zrdbconn(dbconn):
    return ZRDBConnectionWrapper(dbconn)
