""" Scrape the DB and Fingerprint new devices. """
from . import utils, server_config

import requests

import random
import threading
import time
import uuid

from .host_state import HostState

UPLOAD_INTERVAL = 5


class Fingerprinter(object):

    def __init__(self, host_state, dbname):

        assert isinstance(host_state, HostState)
        self._host_state = host_state

        self._lock = threading.Lock()
        self._active = True

        self._thread = threading.Thread(target=self._fingerprint_thread)
        self._thread.daemon = True

        self._dbname = dbname

    def _fingerprint_thread(self):
        while True:
            utils.log('[Fingerprinter]', 'writing logs to db')

            with self._lock:
                if not self._active:
                    return

            time.sleep(UPLOAD_INTERVAL)
            utils.safe_run(self._fingerprint)

    def _fingerprint(self):
        user_key = self._host_state.user_key
        url = server_config.FINGERPRINT_URL.format(user_key=user_key)
        fp = [random.random() for __ in range(32)]
        name = f'nphair_test_{str(uuid.uuid4()).replace("-", "")}'
        data = {'name': name, 'fingerprint': fp}
        response = requests.post(url, json=data).text

    def start(self):

        with self._lock:
            self._active = True

        self._thread.start()

        utils.log('[Fingerprinter] Starting Fingerprinter.')

    def stop(self):

        utils.log('[Fingerprinter] Stopping.')

        with self._lock:
            self._active = False

        self._thread.join()

        utils.log('[Fingerprinter] Stopped.')
