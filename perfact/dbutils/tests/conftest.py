#!/usr/bin/python3
from typing import Any

import pytest
from pytest_postgresql.janitor import DatabaseJanitor
import psycopg2


@pytest.fixture(scope='function')
def postgresql(
        postgresql_proc: Any
) -> Any:
    """A PostgreSQL database."""
    with DatabaseJanitor(
        user=postgresql_proc.user,
        host=postgresql_proc.host,
        port=postgresql_proc.port,
        dbname=postgresql_proc.dbname,
        version=postgresql_proc.version,
        password=postgresql_proc.password,
    ):
        with psycopg2.connect(
            dbname=postgresql_proc.dbname,
            user=postgresql_proc.user,
            password=postgresql_proc.password,
            host=postgresql_proc.host,
            port=postgresql_proc.port,
        ) as db_connection:
            yield db_connection
