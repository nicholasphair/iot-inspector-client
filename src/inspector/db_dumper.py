"""
Anonymizes and uploads DNS and flow data to cloud.

"""
from pathlib import Path
from queue import Empty
import datetime
import json
import requests
import sqlite3
import threading
import time
import traceback

from . import server_config
from . import utils

UPLOAD_INTERVAL = 5


class DBDumper(object):
    SCHEMA = Path(__file__).resolve().parents[0] / 'schema.sql'

    def __init__(self, dbname, queue):

        self._lock = threading.Lock()
        self._active = True

        self._thread = threading.Thread(target=self._upload_thread)
        self._thread.daemon = True

        self._dbname = dbname
        self._queue = queue

    def _upload_thread(self):
        self._conn = sqlite3.connect(self._dbname)

        while not utils.safe_run(self._init_db):
            time.sleep(2)

        while True:
            utils.log('[DBDump]', 'writing logs to db')
            time.sleep(UPLOAD_INTERVAL)

            with self._lock:
                if not self._active:
                    return
            utils.safe_run(self._dump_data)

    def _init_db(self):
        with open(DBDumper.SCHEMA, 'r') as f:
            schema = f.read()
        self._conn.executescript(schema)
        self._conn.commit()
        return True

    def _dump_data(self):
        try:
            data = self._queue.get(timeout=10)
        except Empty:
            return


        ddata = utils.deserialize_data(data)

        print(f'got data {ddata}')
        self._conn.commit()

    def _table_exists(self, table_name):
        query = f"SELECT count(name) FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        cur = self._conn.execute(query)
        return cur.fetchone()[0] == 1

    def start(self):

        with self._lock:
            self._active = True

        self._thread.start()

        utils.log('[DBDump] Start writing data to the database.')

    def stop(self):

        utils.log('[DBDump] Stopping.')

        with self._lock:
            self._active = False

        self._thread.join()

        utils.log('[DBDump] Stopped.')


