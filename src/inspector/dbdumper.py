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
        self._conn = sqlite3.connect(self._dbname, check_same_thread=False)

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

    def _flow_to_record(self, flow):
        k, value = flow
        key = json.loads(k)

        device_id = f"'{key[0]}'"
        device_port = str(key[1])
        remote_ip = f"'{key[2]}'"
        remote_port = str(key[3])
        protocol = f"'{key[4]}'"
        in_byte_count = value['inbound_byte_count']
        out_byte_count = value['outbound_byte_count']

        # NB (nphair): Not sure about these fields.
        is_inspected = '0'
        remote_hostname = remote_ip
        remote_hostname_info_source = "''"
        remote_ip_country = "''"
        remote_reg_domain = "''"
        remote_tracker = "''"
        remote_web_xray = "''"
        total_byte_count = in_byte_count + out_byte_count
        ts = int(value['internal_flow_ts_min'])
        ts_min = value['internal_flow_ts_min']
        ts_mod10 = ts % 10
        ts_mod3600 = ts % 3600
        ts_mod60 = ts % 60
        ts_mod600 = ts % 600
        user_key = f'test_{str(uuid.uuid4()).replace("-", "")}'
        user_key = f"'{user_key}'"
        return ', '.join((
            device_id,
            device_port,
            str(in_byte_count),
            is_inspected,
            str(out_byte_count),
            protocol,
            remote_hostname,
            remote_hostname_info_source,
            remote_ip,
            remote_ip_country,
            remote_port,
            remote_reg_domain,
            remote_tracker,
            remote_web_xray,
            str(total_byte_count),
            str(ts),
            str(ts_min),
            str(ts_mod10),
            str(ts_mod3600),
            str(ts_mod60),
            str(ts_mod600),
            user_key,
        ))

    def _dns_to_records(self, dns):
        k, value = dns
        key = json.loads(k)

        user_key = f'test_{str(uuid.uuid4()).replace("-", "")}'
        user_key = f"'{user_key}'"
        device_id = f"'{key[0]}'"
        ts = str(int(time.time()))
        hostname = f"'{key[1]}'"
        ip = f"'{key[2]}'"
        device_port = str(key[3])
        data = ', '.join((user_key, device_id, ts, ip, hostname, device_port))
        return [f"{data}, '{ds}'" for ds in value]

    def _write_to_db(self, data):
        if data:
            print(data)
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

        for device_id, items in netdisco_dict.items():
            for ndd in items:
                dhcp_hostname = ndd.get('host')
                device_ip = ndd.get('host')
                device_name = ndd.get('model_name')
                device_type = ndd.get('upnp_device_type')
                device_vendor = ndd.get('manufacturer')
                device_oui = device_id
                vals = ', '.join((
                    f"'{device_id}'",
                    f"'{dhcp_hostname}'",
                    f"'{device_ip}'",
                    f"'{device_name}'",
                    f"'{device_type}'",
                    f"'{device_vendor}'",
                    f"'{device_oui}'",
                    f"'ua_list'",    # TODO
                    f"0",    # TODO
                    f"0",    # TODO
                    f"{client_ts}",
                    f"0",    # TODO
                ))
                self._conn.execute(f"INSERT INTO devices VALUES ({vals})")

        for dns in dns_dict.items():
            for record in self._dns_to_records(dns):
                print(record)
                self._conn.execute(f"INSERT INTO dns VALUES ({record})")

        for flow in flow_dict.items():
            record = self._flow_to_record(flow)
            self._conn.execute(f"INSERT INTO flows VALUES ({record})")

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
