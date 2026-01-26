# test cases for crud module
from typing import Any
from ..crud import create, update, delete, read
from ..conn import Connection as DBConnection
import psycopg2
import psycopg
from pytest_postgresql import factories
from pytest_postgresql.janitor import DatabaseJanitor
import pytest


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


postgresql_proc = factories.postgresql_proc(
    load=[load_database],
)


@pytest.fixture(scope='function')
def postgresql(postgresql_proc: Any) -> Any:
    """A PostgreSQL database."""
    with DatabaseJanitor(
        user=postgresql_proc.user,
        host=postgresql_proc.host,
        port=postgresql_proc.port,
        dbname=postgresql_proc.dbname,
        version=postgresql_proc.version,
        password=postgresql_proc.password,
    ) as janitor:
        janitor.load(load_database)
        with psycopg2.connect(
            dbname=postgresql_proc.dbname,
            user=postgresql_proc.user,
            password=postgresql_proc.password,
            host=postgresql_proc.host,
            port=postgresql_proc.port,
        ) as db_connection:
            yield db_connection


def test_create(postgresql):
    """
    Test the create function.
    """
    conn = DBConnection(postgresql)
    # create entry
    payload = {'appuser_name': 'Alice', 'appuser_fullname': 'Alice Smith'}
    res = create(conn=conn, table='appuser', payload=payload)
    assert res['appuser_id'] == 1
    assert res['appuser_name'] == 'Alice'
    assert res['appuser_fullname'] == 'Alice Smith'


def test_create_default_values(postgresql):
    """
    Test the create function with default values.
    """
    conn = DBConnection(postgresql)
    # create entry with default values
    res = create(conn=conn, table='appuser')
    assert res['appuser_id'] == 1
    assert res['appuser_name'] is None
    assert res['appuser_fullname'] is None


def test_create_prevented(postgresql):
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
    assert create(conn=conn, table='appuser') is None
    res = conn.execute('select * from appuser')
    assert res.tuples == []


def test_update(postgresql):
    """
    Test the update function.
    """
    conn = DBConnection(postgresql)
    # create initial entry
    payload = {'appuser_name': 'bob', 'appuser_fullname': 'Bob Smith'}
    inserted = create(conn=conn, table='appuser', payload=payload)
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
    inserted = create(conn=conn, table='appuser', payload=payload)
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
    # create initial entry
    payload = {'appuser_name': 'Eve', 'appuser_fullname': 'Eve Adams'}
    inserted = create(conn=conn, table='appuser', payload=payload)
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
    # create initial entry
    payload = {'appuser_name': 'Frank', 'appuser_fullname': 'Frank Miller'}
    inserted = create(conn=conn, table='appuser', payload=payload)
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
    # create initial entry
    payload = {'appuser_name': 'Diana', 'appuser_fullname': 'Diana Prince'}
    inserted = create(conn=conn, table='appuser', payload=payload)
    # Delete entry
    ident = {'appuser_id': inserted['appuser_id']}
    delete(conn=conn, table='appuser', ident=ident)
    # Verify deletion
    res = conn.execute(
        "select * from appuser where appuser_id = %(appuser_id)s",
        appuser_id=inserted['appuser_id'])
    deleted = list(res.dicts())
    assert len(deleted) == 0


def _setup_read_testdata(conn):
    """
    Setup testdata for tests of the read operation
    """
    payload = {
        'appuser_name': 'Syril',
        'appuser_fullname': 'Syril Karn'
    }
    create(conn=conn, table='appuser', payload=payload)
    payload = {
        'appuser_name': 'Luthen',
        'appuser_fullname': 'Luthen Rael'
    }
    create(conn=conn, table='appuser', payload=payload)


def test_read_simple(postgresql):
    """
    Test a simple select all.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)

    selected = read(
        conn=conn,
        table='appuser',
    )
    assert len(selected) == 2
    # All columns must be selected
    assert len(selected[0]) == 5


def test_read_columns(postgresql):
    """
    Test a read operation with specified columns.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)

    selected = read(
        conn=conn,
        columns=['appuser_fullname'],
        table='appuser',
    )
    assert len(selected[0]) == 1
    assert 'appuser_fullname' in selected[0]

    selected = read(
        conn=conn,
        columns=['appuser_fullname', 'appuser_name'],
        table='appuser',
    )
    assert len(selected[0]) == 2
    assert 'appuser_fullname' in selected[0]
    assert 'appuser_name' in selected[0]


def test_read_ident(postgresql):
    """
    Test a read operation with specified ident.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)

    selected = read(
        conn=conn,
        table='appuser',
        ident={
            'appuser_name': 'Luthen'
        }
    )
    assert len(selected) == 1
    # Test with explicitly setting ident to None
    selected = read(
        conn=conn,
        table='appuser',
        ident=None
    )
    assert len(selected) == 2


def test_read_where(postgresql):
    """
    Test a read operation with specified where expression.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)
    # Test where with stmt and payload
    selected = read(
        conn=conn,
        table='appuser',
        where={
            'stmt': (
                'appuser_modtime <= now() and '
                'appuser_name = %(appuser_name)s'
            ),
            'payload': {
                'appuser_name': 'Luthen'
            },
        }
    )
    assert len(selected) == 1
    assert selected[0]['appuser_name'] == 'Luthen'
    # Test where without payload
    selected = read(
        conn=conn,
        table='appuser',
        where={
            'stmt': (
                'appuser_modtime <= now() and '
                'appuser_id < 10'
            ),
        }
    )
    assert len(selected) == 2
    # Test select without any rows returned
    selected = read(
        conn=conn,
        table='appuser',
        where={
            'stmt': (
                'appuser_name = %(appuser_name)s'
            ),
            'payload': {
                'appuser_name': 'Cassian'
            },
        }
    )
    assert not selected


def test_read_orderby(postgresql):
    """
    Test a read operation with specified order by expression.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)
    # Simple order by with list of str
    selected = read(
        conn=conn,
        table='appuser',
        orderby=['appuser_name']
    )
    assert selected[0]['appuser_name'] == 'Luthen'
    # Test order by with tuple
    selected = read(
        conn=conn,
        table='appuser',
        orderby=[('appuser_name', 'desc')]
    )
    assert selected[0]['appuser_name'] == 'Syril'
    # Test order by with mix of tuple and str
    selected = read(
        conn=conn,
        table='appuser',
        orderby=[('appuser_name', 'desc'), 'appuser_fullname']
    )
    assert selected[0]['appuser_name'] == 'Syril'
    # Test wrong sort direction
    with pytest.raises(ValueError):
        selected = read(
            conn=conn,
            table='appuser',
            orderby=[('appuser_name', '; select 1;')]
        )
    # Test incomplete tuple
    with pytest.raises(ValueError):
        selected = read(
            conn=conn,
            table='appuser',
            orderby=[tuple('appuser_name')]
        )


def test_read_limit(postgresql):
    """
    Test a read operation with specified limit.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)
    selected = read(
        conn=conn,
        table='appuser',
        limit=1,
    )
    assert len(selected) == 1


def test_read_for_update(postgresql):
    """
    Test a read operation with for_update set.
    """
    conn = DBConnection(postgresql)
    _setup_read_testdata(conn=conn)
    read(
        conn=conn,
        table='appuser',
        for_update=True,
    )

    locks = conn.execute("""
        select mode
        from pg_locks
        join pg_class
          on pg_locks.relation = pg_class.oid
        WHERE pg_class.relname = 'appuser'
          AND pg_locks.mode = 'RowExclusiveLock'
    """)

    assert locks
