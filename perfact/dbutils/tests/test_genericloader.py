import os

import pytest

from ..conn import Connection as DBConnection
from ..crud import create
from ..genericloader import load_records


@pytest.fixture(scope="function")
def conn(postgresql):
    """
    Create records in test
    """
    conn = DBConnection(postgresql)
    base = os.path.dirname(__file__)
    setup_file = os.path.join(base, "test_genericloader_setup.sql")
    with open(setup_file, "r", encoding="utf-8") as f:
        sql = f.read()
        conn.execute(sql)
    create_test_data(conn)
    yield conn


def create_test_data(dbconn):
    testlc_data = [
        {
            "testlc_id": 1,
            "testlc_name": "running",
        },
        {
            "testlc_id": 2,
            "testlc_name": "stopped",
        },
        {
            "testlc_id": 3,
            "testlc_name": "explosion",
        },
    ]
    for testlc_payload in testlc_data:
        create(
            conn=dbconn,
            table="testlc",
            payload=testlc_payload,
        )

    testlct_data = [
        {
            "testlct_id": 1,
            "testlct_from_testlc_id": 1,
            "testlct_to_testlc_id": 2,
            "testlct_testlc_id": 1,
            "testlct_name": "Stop machine",
        },
        {
            "testlct_id": 2,
            "testlct_from_testlc_id": 2,
            "testlct_to_testlc_id": 1,
            "testlct_name": "Start machine",
        },
        {
            "testlct_id": 3,
            "testlct_from_testlc_id": 1,
            "testlct_to_testlc_id": 3,
            "testlct_name": "Machine explodes",
        },
    ]
    for testlct_payload in testlct_data:
        create(
            conn=dbconn,
            table="testlct",
            payload=testlct_payload,
        )


def dummy_selfilter_generator(table, column):
    return "true"


def selfilter_generator_no_records(table, column):
    return "false"


def test_load_records_simple(conn):
    rows = load_records(
        conn=conn,
        table="testlc",
        columns=["testlc_id", "testlc_name"],
        add_lookups=False,
        selfilter_generator=dummy_selfilter_generator,
    )
    assert len(rows) == 3
    assert "lookup_testlc_id" not in rows[0]
    assert "testlc_id" in rows[0]
    assert "testlc_name" in rows[0]

    # No selfilter
    rows = load_records(
        conn=conn,
        table="testlc",
        columns=["testlc_id", "testlc_name"],
        add_lookups=False,
    )
    assert len(rows) == 3
    assert "lookup_testlc_id" not in rows[0]
    assert "testlc_id" in rows[0]
    assert "testlc_name" in rows[0]


def test_load_records_no_rows(conn):
    rows = load_records(
        conn=conn,
        table="testlc",
        columns=["testlc_id", "testlc_name"],
        add_lookups=False,
        selfilter_generator=selfilter_generator_no_records,
    )
    assert len(rows) == 0


def test_load_records_ident(conn):
    rows = load_records(
        conn=conn,
        table="testlc",
        columns=["testlc_id", "testlc_name"],
        add_lookups=False,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlc_id": 1},
    )
    assert len(rows) == 1
    assert rows[0]["testlc_id"] == 1


def test_load_records_lookups(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
            "testlct_name",
            "testlct_from_testlc_id",
            "testlct_to_testlc_id",
            "testlct_testlc_id",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
    )
    assert len(rows) == 3
    assert "lookup_testlct_id" in rows[0]

    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
            "testlct_name",
            "testlct_from_testlc_id",
            "testlct_to_testlc_id",
            "testlct_testlc_id",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlct_id": 1},
    )
    assert len(rows) == 1
    assert rows[0]["lookup_testlct_id"] == "Stop machine"
    assert rows[0]["lookup_testlct_from_testlc_id"] == "running"
    assert rows[0]["lookup_testlct_to_testlc_id"] == "stopped"
    assert rows[0]["lookup_testlct_testlc_id"] == "running"

    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_name",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlct_id": 1},
    )
    assert len(rows) == 1


def test_load_records_alias(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
        ],
        add_lookups=False,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlct_id": 1},
        alias={"somecalculated_col": "1 < 2"},
    )
    assert len(rows) == 1
    assert "somecalculated_col" in rows[0]
    assert rows[0]["somecalculated_col"]

    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlct_id": 1},
        alias={"testlct_from_testlc_id": "3"},
    )
    assert len(rows) == 1
    assert "lookup_testlct_from_testlc_id" in rows[0]
    assert rows[0]["lookup_testlct_from_testlc_id"] == "explosion"


def test_load_records_joins(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
            "testlct_testlc_id",
            "testlc_id",
            "testlc_name",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
        ident={"testlct_id": 1},
        joins="join testlc on testlc_id = testlct_to_testlc_id",
    )
    assert len(rows) == 1
    assert rows[0]["lookup_testlct_testlc_id"] == "running"
    assert rows[0]["lookup_testlc_id"] == "stopped"
    assert rows[0]["testlc_name"] == "stopped"


def test_load_records_where(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
        ],
        add_lookups=False,
        selfilter_generator=dummy_selfilter_generator,
        where="testlct_id = %(testlct_id)s",
        payload={"testlct_id": 1},
    )
    assert len(rows) == 1
    assert rows[0]["testlct_id"] == 1


def test_load_records_orderby_with_limit(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
        ],
        add_lookups=False,
        selfilter_generator=dummy_selfilter_generator,
        orderby="testlct_id desc",
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0]["testlct_id"] == 3


def test_load_records_joins_where_orderby_with_payload(conn):
    rows = load_records(
        conn=conn,
        table="testlct",
        columns=[
            "testlct_id",
            "testlc_id",
        ],
        add_lookups=True,
        selfilter_generator=dummy_selfilter_generator,
        orderby="testlc_id = %(testlc_id)s desc nulls last",
        where="testlc_id <= %(testlc_id)s or testlc_id is null",
        joins=(
            "left join testlc on testlc_id = %(testlc_id)s "
            "and testlct_to_testlc_id = testlc_id"
        ),
        payload={"testlc_id": 3},
    )
    assert len(rows) == 3
    assert rows[0]["testlct_id"] == 3
    assert rows[0]["testlc_id"] == 3


def test_load_records_exceptions(conn):
    with pytest.raises(ValueError):
        load_records(
            conn=conn,
            columns=[],
            table="testlct",
            add_lookups=True,
            selfilter_generator=dummy_selfilter_generator,
            orderby="testlc_id = %(testlc_id)s desc nulls last",
            where="(testlc_id <= %(testlc_id)s or testlc_id is null)",
            joins=(
                "left join testlc on testlc_id = %(testlc_id)s "
                "and testlct_to_testlc_id = testlc_id"
            ),
            payload={"testlc_id": 3},
        )
