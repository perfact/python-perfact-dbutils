from psycopg2 import sql

from ..conn import Connection, wrap_zrdbconn


def test_psycopg(postgresql):
    """
    Test basic usage with a psycopg test connection.
    """
    conn = Connection(postgresql)
    res = conn.execute("""
      select now() as ts
    """)
    assert res.names == ("ts",)
    assert len(res.tuples) == 1
    assert len(list(res.rows())) == 1
    assert len(list(res.dicts())) == 1
    # Query not returning anything
    res = conn.execute("create table appuser (appuser_id bigint)")
    assert len(res.tuples) == 0


class MockZRDBConnection:
    def __init__(self, conn):
        self._v_database_connection = self
        self.conn = conn

    def query(self, query, query_data=None):
        with self.conn.cursor() as cur:
            cur.execute(query, query_data)
            if not cur.description:
                return (), []
            return (
                [{"name": col.name} for col in cur.description],
                cur.fetchall(),
            )

    def getcursor(self):
        return self.conn


def generate_query(src__):
    assert src__
    return "select 5*6 as bla"


def test_wrapper(postgresql):
    """
    Test the wrapper for ZRDBConnection objects - although we mock them here.
    """
    mock = MockZRDBConnection(postgresql)
    conn = wrap_zrdbconn(mock)
    # Regular query
    res = conn.execute("select now() as ts")
    assert res.names == ("ts",)
    # Test wrapper with composed sql
    query = sql.SQL("select now() as ts").format()
    res = conn.execute(query)
    assert res.names == ("ts",)
    # Query generator, mocking ZSQLMethod
    res = conn.execute(generate_query)
    assert res.names == ("bla",)
    # Query not returning anything
    res = conn.execute("create table appuser (appuser_id bigint)")
    assert len(res.tuples) == 0
