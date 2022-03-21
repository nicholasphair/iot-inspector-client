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
import uuid

from . import server_config
from . import utils


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
        self._write_to_db(ddata)

    def _write_to_db(self, data):
        client_status_text = data['client_status_text']
        dns_dict = data['dns_dict']
        syn_scan_dict = data['syn_scan_dict']
        flow_dict = data['flow_dict']
        device_dict = data['device_dict']
        ua_dict = data['ua_dict']
        dhcp_dict = data['dhcp_dict']
        resolver_dict = data['resolver_dict']
        client_version = data['client_version']
        tls_dict_list = data['tls_dict_list']
        netdisco_dict = data['netdisco_dict']
        duration = data['duration']
        client_ts = data['client_ts']

        print(netdisco_dict)
        for device, items in netdisco_dict.items():
            for ndd in items:
                device_id = ndd['serial']
                dhcp_hostname = ndd['host']
                user_key = f'nphair_test_{str(uuid.uuid4()).replace("-", "")}'
                device_ip = ndd['host']
                device_name = ndd['model_name']
                device_type = ndd['upnp_device_type']
                device_vendor = ndd['manufacturer']
                device_oui = device
                netdisco_name = ndd['name']
                fb_name = 'baz'
                vals = ', '.join((
                    f"'{user_key}'",
                    f"'{device_id}'",
                    f"'{dhcp_hostname}'",
                    f"'{device_ip}'",
                    f"'{device_name}'",
                    f"'{device_type}'",
                    f"'{device_vendor}'",
                    f"'{device_oui}'",
                    f"'{netdisco_name}'",
                    f"'{fb_name}'",
                ))
                self._conn.execute(f"INSERT INTO devices VALUES ({vals})")
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
