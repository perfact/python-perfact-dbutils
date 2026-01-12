from ..conn import Connection, wrap_zrdbconn


def test_psycopg(postgresql):
    """
    Test basic usage with a psycopg test connection.
    """
    conn = Connection(postgresql)
    res = conn.execute("""
      select now() as ts
    """)
    assert res.names == ('ts', )
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
        rows = self.conn.execute(query, query_data)
        if not rows.description:
            return (), []
        return (
            [{'name': col.name} for col in rows.description],
            rows.fetchall(),
        )


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
    assert res.names == ('ts', )
    # Query generator, mocking ZSQLMethod
    res = conn.execute(generate_query)
    assert res.names == ('bla', )
    # Query not returning anything
    res = conn.execute("create table appuser (appuser_id bigint)")
    assert len(res.tuples) == 0
