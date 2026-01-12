# test cases for crud module
from typing import Any
from ..crud import insert, update, delete
from ..conn import Connection as DBConnection
import psycopg
from pytest_postgresql import factories
import pytest_postgresql.factories


def load_database(**kwargs: Any) -> None:
    db_connection: psycopg.Connection = psycopg.connect(**kwargs)
    with db_connection.cursor() as cur:
        # generic initialization for all tests
        cur.execute(
            "CREATE TABLE appuser "
            "(appuser_id serial PRIMARY KEY, "
            "appuser_author varchar, "
            "appuser_modtime timestamp default current_timestamp, "
            "appuser_name varchar, "
            "appuser_fullname varchar);"
        )
        cur.execute(
            "create or replace function db_username() "
            "returns text as $$ "
            "begin "
            "   return 'test_user'; "
            "end; "
            "$$ language plpgsql;")
        db_connection.commit()


postgresql_proc = pytest_postgresql.factories.postgresql_proc(
    load=[load_database],
)

postgresql = factories.postgresql(
    "postgresql_proc",
)


def test_insert(postgresql):
    """
    Test the insert function.
    """
    conn = DBConnection(postgresql)
    # Insert entry
    payload = {'appuser_name': 'Alice', 'appuser_fullname': 'Alice Smith'}
    res = insert(conn=conn, table='appuser', payload=payload)
    assert res['appuser_id'] == 1
    assert res['appuser_name'] == 'Alice'
    assert res['appuser_fullname'] == 'Alice Smith'


def test_insert_default_values(postgresql):
    """
    Test the insert function with default values.
    """
    conn = DBConnection(postgresql)
    # Insert entry with default values
    res = insert(conn=conn, table='appuser')
    assert res['appuser_id'] == 1
    assert res['appuser_name'] is None
    assert res['appuser_fullname'] is None


def test_insert_prevented(postgresql):
    """
    Test that an insert that is prevented by a trigger returns None
    """
    conn = DBConnection(postgresql)
    conn.execute("""
        create or replace function prevent_inserts()
        returns trigger language plpgsql as $function$
        begin
          return null;
        end;
        $function$;
        create trigger prevent_inserts before insert on appuser
          for each row execute function prevent_inserts();
    """)
    assert insert(conn=conn, table='appuser') is None
    res = conn.execute('select * from appuser')
    assert res.tuples == []


def test_update(postgresql):
    """
    Test the update function.
    """
    conn = DBConnection(postgresql)
    # Insert initial entry
    payload = {'appuser_name': 'bob', 'appuser_fullname': 'Bob Smith'}
    inserted = insert(conn=conn, table='appuser', payload=payload)
    # Update entry
    ident = {'appuser_id': inserted['appuser_id']}
    update_payload = {'appuser_fullname': 'Robert Smith'}
    update(
        conn=conn, table='appuser', ident=ident, payload=update_payload)
    # Verify update
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    updated = list(res.dicts())[0]
    assert updated['appuser_name'] == 'bob'
    assert updated['appuser_fullname'] == 'Robert Smith'
    assert updated['appuser_author'] == 'test_user'
    assert updated['appuser_modtime'] is not None


def test_update_ident_is_null(postgresql):
    """
    Test the update function with ident containing None value.
    """
    conn = DBConnection(postgresql)
    payload = {'appuser_name': 'Charlie', 'appuser_fullname': None}
    inserted = insert(conn=conn, table='appuser', payload=payload)
    # Update entry where age is null
    ident = {'appuser_fullname': None, 'appuser_name': 'Charlie'}
    update_payload = {'appuser_fullname': 'Charlie Brown'}
    update(
        conn=conn, table='appuser', ident=ident, payload=update_payload)
    # Verify update
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    updated = list(res.dicts())[0]
    assert updated['appuser_name'] == 'Charlie'
    assert updated['appuser_fullname'] == 'Charlie Brown'
    assert updated['appuser_author'] == 'test_user'
    assert updated['appuser_modtime'] is not None


def test_update_no_auditmode(postgresql):
    """
    Test the update function with auditmode disabled.
    also tests update with only one column in up
    """
    conn = DBConnection(postgresql)
    # Insert initial entry
    payload = {'appuser_name': 'Eve', 'appuser_fullname': 'Eve Adams'}
    inserted = insert(conn=conn, table='appuser', payload=payload)
    # Update entry with auditmode disabled
    ident = {'appuser_id': inserted['appuser_id']}
    update_payload = {'appuser_fullname': 'Evelyn Adams'}
    update(
        conn=conn, table='appuser', ident=ident,
        payload=update_payload, auditmode=False)
    # Verify update
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    updated = list(res.dicts())[0]
    assert updated['appuser_name'] == 'Eve'
    assert updated['appuser_fullname'] == 'Evelyn Adams'
    assert updated['appuser_author'] == inserted['appuser_author']
    assert updated['appuser_modtime'] == inserted['appuser_modtime']


def test_update_in_ident(postgresql):
    """
    Test the update function where a column in ident is also in payload.
    """
    conn = DBConnection(postgresql)
    # Insert initial entry
    payload = {'appuser_name': 'Frank', 'appuser_fullname': 'Frank Miller'}
    inserted = insert(conn=conn, table='appuser', payload=payload)
    # Update entry where appuser_name is also in ident
    ident = {'appuser_id': inserted['appuser_id'], 'appuser_name': 'Frank'}
    update_payload = {
        'appuser_name': 'Franklin', 'appuser_fullname': 'Frank Miller Jr.'}
    update(
        conn=conn, table='appuser', ident=ident, payload=update_payload)
    # Verify update
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    updated = list(res.dicts())[0]
    assert updated['appuser_name'] == 'Franklin'
    assert updated['appuser_fullname'] == 'Frank Miller Jr.'
    assert updated['appuser_author'] == 'test_user'
    assert updated['appuser_modtime'] is not None


def test_delete(postgresql):
    """
    Test the delete function.
    """
    conn = DBConnection(postgresql)
    # Insert initial entry
    payload = {'appuser_name': 'Diana', 'appuser_fullname': 'Diana Prince'}
    inserted = insert(conn=conn, table='appuser', payload=payload)
    # Delete entry
    ident = {'appuser_id': inserted['appuser_id']}
    delete(conn=conn, table='appuser', ident=ident)
    # Verify deletion
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    deleted = list(res.dicts())
    assert len(deleted) == 0
