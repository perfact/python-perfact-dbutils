# test cases for crud module
import pytest

from ..conn import Connection as DBConnection
from ..schemainfo import get_columns


@pytest.fixture(scope="function")
def conn(postgresql):
    """
    Create records in test, testlc, testlct.
    """
    conn = DBConnection(postgresql)
    conn.execute(
        "CREATE TABLE appuser "
        "(appuser_id serial PRIMARY KEY, "
        "appuser_author varchar, "
        "appuser_modtime timestamp default current_timestamp, "
        "appuser_name varchar, "
        "appuser_fullname varchar);"
    )
    conn.execute(
        "create or replace function db_username() "
        "returns text as $$ "
        "begin "
        "   return 'test_user'; "
        "end; "
        "$$ language plpgsql;"
    )
    yield conn


def test_get_columns_fullname(conn):
    """
    Test the get_columns function
    """
    res = get_columns(conn=conn, table="appuser", full_colname=True)
    print(res)
    assert len(res) == 5
    assert "appuser_id" in res


def test_get_columns_colname_only(conn):
    """
    Test the get_columns function
    """
    res = get_columns(conn=conn, table="appuser", full_colname=False)
    assert len(res) == 5
    assert "id" in res


def test_get_columns_with_no_columns(conn):
    """
    Test the get_columns function for table that has no columns.
    """
    res = get_columns(
        conn=conn,
        table="empty_table",
    )
    assert len(res) == 0
