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


class SecureComputer(object):

    def __init__(self, dbname):

        self._lock = threading.Lock()
        self._active = True

        self._thread = threading.Thread(target=self._compute_thread)
        self._thread.daemon = True

        self._dbname = dbname

    def _compute_thread(self):

        while not utils.safe_run(self._init_db):
            time.sleep(2)

        while True:
            utils.log('[SecureCompute]', 'writing logs to db')

            with self._lock:
                if not self._active:
                    self._conn.close()
                    return
            utils.safe_run(self._compute)

    def _init_db(self):
        if not Path(self._dbname).exists():
            utils.log('[SecureCompute]', f'error: database {self._dbname} not found.')
            return False

        self._conn = sqlite3.connect(self._dbname, check_same_thread=False)
        return True


    def _compute(self):
        # Get Peers.
        partner_response = requests.get(server_config.PARTNER_URL)
        partner = partner_response.json()
        if not partner.get('success'):
            utils.log('[SecureCompute]', f'error. not enough peers to compute with')
            return

        # Get Model.
        model_response = requests.get(server_config.MODEL_URL, stream=True)
        # binary data can be read from the raw object...
        # model_response.raw
        time.sleep(10)

        utils.log('[SecureCompute]', f'doing my computations...')


    def start(self):

        with self._lock:
            self._active = True

        self._thread.start()

        utils.log('[SecureCompute] Start writing data to the database.')

    def stop(self):

        utils.log('[SecureCompute] Stopping.')

        with self._lock:
            self._active = False

        self._thread.join()

        utils.log('[SecureCompute] Stopped.')
