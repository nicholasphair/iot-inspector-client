import pytest
import sqlite3
from src.inspector.db_dumper import DBDumper


class TestDBDumper:
    def test_init_db(self):
        dumper = DBDumper(':memory:', None)
        dumper._init_db()
        assert dumper._table_exists('devices')
        assert dumper._table_exists('dns')
        assert dumper._table_exists('tls')
        assert dumper._table_exists('flows')
