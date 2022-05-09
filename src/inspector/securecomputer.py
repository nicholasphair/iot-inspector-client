"""
Anonymizes and uploads DNS and flow data to cloud.

"""
from pathlib import Path
from queue import Empty
import crypten
import crypten.communicator as comm
import datetime
import itertools
import json
import requests
import sqlite3
import torch
import threading
import time
import traceback
import uuid
import os

from . import server_config
from . import utils
from .host_state import HostState
from crypten.config import WorkerConfig, cfg


class SecureComputer(object):

    def __init__(self, host_state: HostState, dbname):
        self._host_state = host_state
        self._lock = threading.Lock()
        self._active = True

        self._thread = threading.Thread(target=self._compute_thread)
        self._thread.daemon = True

        self._dbname = dbname

        self._config_dir = Path.home() / f'princeton-iot-inspector/.configs/{os.getpid()}'
        self._config_dir.mkdir(parents=True, exist_ok=True)

    @property
    def logger(self):
        return utils.logger("secure_compute")

    def _compute_thread(self):

        while not utils.safe_run(self._init_db):
            time.sleep(2)

        user_config = utils.get_user_config()

        while True:
            utils.log('[SecureCompute]', 'writing logs to db')

            with self._lock:
                if not self._active:
                    self._conn.close()
                    return

            time.sleep(user_config["partner_interval"])
            utils.safe_run(self._compute)

    def _init_db(self):
        if not Path(self._dbname).exists():
            utils.log('[SecureCompute]', f'error: database {self._dbname} not found.')
            return False

        self._conn = sqlite3.connect(self._dbname, check_same_thread=False)
        return True

    def _should_compute(self):
        return (self._config_dir / 'start_computation').exists()

    def _should_be_peer(self):
        return (self._config_dir / 'start_peer').exists()

    def _heartbeat(self):
        """Notify the server that the client is available as a peer for
        computation."""
        user_key = self._host_state.user_key
        url = server_config.HEARTBEAT_URL.format(user_key=user_key)
        self.logger.debug("Submitting heartbeat to %s", url)
        resp = requests.post(url)

        if resp.status_code >= 400:
            content = resp.text
            self.logger.error(
                "Status code %d trying to submit heartbeat: %s",
                resp.status_code,
                content.replace("\n", "\\n"),
            )

            return None
        else:
            return resp.json()

    def _get_partners(self):
        # Get two partners to perform secure MPC
        user_key = self._host_state.user_key
        partners = []

        for _ in range(2):
            url = server_config.PARTNER_URL.format(user_key=user_key)
            partner_response = requests.post(url)
            partner = partner_response.json()

            if partner_response.status_code >= 400 or not partner.get('success'):
                self.logger.error("Not enough peers to compute with")
                return None

            partners.append(partner)

        return partners

    def _separate(self):
        self.logger.info("Separating from server")
        user_key = self._host_state.user_key
        url = server_config.SEPARATE_URL.format(user_key=user_key)
        resp = requests.post(url)
        if resp.status_code >= 400:
            self.logger.error(
                "Received code %d while separating peer: %s",
                resp.status_code,
                repr(resp.text),
            )

    def _compute(self):
        resp = self._heartbeat()
        user_key = self._host_state.user_key

        if self._should_compute():
            self.logger.info('Requesting a partner to compute with...')
            # Get Peers.
            try:
                if (partners := self._get_partners()) is None:
                    return
                # Get Model.
                model_response = requests.get(server_config.MODEL_URL, stream=True)
                # binary data can be read from the raw object...
                # model_response.raw

                self.logger.info(f"{partners = }")
                self._run_evaluation(is_initiator=True)
            finally:
                # Stop seeking to perform a model computation now that
                # computation has finished successfully
                (self._config_dir / 'start_computation').unlink()
                self._separate()
        elif self._should_be_peer():
            try:
                self.logger.info('Waiting to help with a computation...')

                # Check whether the server notified us that we've been
                # assigned to do computation with another client
                self.logger.info(f"{resp = }")
                if resp is None or not resp["has_peer"]:
                    return

                self._run_evaluation(
                    rendezvous_addr=resp["peer"]["address"],
                    party_number=resp["peer"]["index"],
                )
            finally:
                # After finishing the computation, notify the server that
                # we're ready for reassignment
                self._separate()
        else:
            self.logger.info('No work to do... (pid=%d)', os.getpid())

    def _run_evaluation(
        self,
        rendezvous_addr: str = "127.0.0.1",
        rendezvous_port: int = 47072,
        party_number: int = 0,
        is_initiator: bool = False
    ) -> None:
        if is_initiator:
            party_number = 0

        os.environ["WORLD_SIZE"] = "3"
        os.environ["RANK"] = str(party_number)
        os.environ["RENDEZVOUS"] = f"tcp://{rendezvous_addr}:{rendezvous_port}"
        os.environ["DISTRIBUTED_BACKEND"] = "gloo"
        party_mapping = dict((i, [i]) for i in range(3))
        config = WorkerConfig(party_number, party_mapping)

        self.logger.info("Initializing CrypTen")
        crypten.init(worker_config=config)

        x = torch.randn(3)
        x_enc = crypten.cryptensor(x, src=0)
        self.logger.info(f"{x_enc.get_plain_text() = }")

        # Shut down CrypTen
        self.logger.info("Shutting down CrypTen")
        comm.get().shutdown()

    def start(self):

        with self._lock:
            self._active = True

        self._thread.start()

        utils.log('[SecureCompute] Start writing data to the database.')

    def stop(self):

        utils.log('[SecureCompute] Stopping.')

        with self._lock:
            self._active = False

        (self._config_dir / 'start_computation').unlink()
        (self._config_dir / 'start_peer').unlink()
        self._config_dir.rmdir()
        self._thread.join()

        utils.log('[SecureCompute] Stopped.')
