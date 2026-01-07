from typing import Protocol
from dataclasses import dataclass
from abc import abstractmethod


class Namespace():
    """
    Convert a dict to a namespace, allowing access via a.b instead of a['b']
    """
    def __init__(self, data=None, **kw):
        self.__dict__.update(kw)


@dataclass
class Results:
    """
    Object representing the result of a query in a compact way with helper
    functions that yield results in a more usable way.
    """
    names: tuple[str]
    tuples: list[tuple]

    def dicts(self):
        "Generate dicts from result"
        for row in self.tuples:
            yield {key: value for key, value in zip(self.names, row)}

    def rows(self):
        "Generate namespaces from result"
        for row in self.dicts():
            yield Namespace(**row)


class Executor(Protocol):
    @abstractmethod
    def execute(self, query, **args) -> [Results | None]:  # pragma: no cover
        raise NotImplementedError


class Connection:
    """
    Wrapper exposing a nice execute method.
    Is initialized with something that has an execute method like a Connection
    from psycopg.
    """
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, **args) -> [Results | None]:
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
        return Results(
            names=tuple(col.name for col in rows.description),
            tuples=rows.fetchall(),
        )


class ZRDBConnectionWrapper:
    """
    Wrap a ZRDB.Connection into something with a matching execute method
    """
    def __init__(self, conn):
        self.conn = conn._v_database_connection

    def execute(self, query, **args) -> [Results | None]:
        """
        Execute within a Zope transaction
        """
        if not isinstance(query, str):
            # We assume this is a ZSQLMethod
            query = query(src__=1)

        res = self.conn.query(query, query_data=args)
        # Now we have a tuple with the first element containing a list of
        # column descriptions and the second containing the list of results
        if not res[0]:
            return None
        return Results(
            names=tuple(col['name'] for col in res[0]),
            tuples=res[1],
        )


def wrap_zrdbconn(dbconn):
    return ZRDBConnectionWrapper(dbconn)
