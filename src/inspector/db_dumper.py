"""
Anonymizes and uploads DNS and flow data to cloud.

"""
import datetime
import json
import requests
import threading
import time
import traceback

from host_state import HostState
import server_config
import utils


UPLOAD_INTERVAL = 5


class DBDumper(object):

    def __init__(self, host_state):

        assert isinstance(host_state, HostState)
        self._host_state = host_state

        self._lock = threading.Lock()
        self._active = True

        self._thread = threading.Thread(target=self._upload_thread)
        self._thread.daemon = True

        self._last_upload_ts = time.time()

    def _upload_thread(self):

        # Loop until initialized
        while not utils.safe_run(self._upload_initialization):
            time.sleep(2)

        # Continuously upload data
        while True:

            if not self._host_state.is_inspecting():
                self._update_ui_status('Paused inspection.')
                with self._host_state.lock:
                    self._clear_host_state_pending_data()
                time.sleep(2)
                continue

            time.sleep(UPLOAD_INTERVAL)

            with self._lock:
                if not self._active:
                    return

            utils.safe_run(self._upload_data)

    def _upload_initialization(self):
        """Returns True if successfully initialized."""

        # Send client's timezone to server
        ts = time.time()

        utc_offset = int(
            (datetime.datetime.fromtimestamp(ts) -
                datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        )

        utc_offset_url = server_config.UTC_OFFSET_URL.format(
            user_key=self._host_state.user_key,
            offset_seconds=utc_offset
        )

        utils.log('[DATA] Update UTC offset:', utc_offset_url)
        status = requests.get(utc_offset_url).text.strip()
        utils.log('[DATA] Update UTC offset status:', status)

        return 'SUCCESS' == status


    def _upload_data(self):

        # Prepare POST
        user_key = self._host_state.user_key
        url = server_config.SUBMIT_URL.format(user_key=user_key)
        (window_duration, post_data) = self._prepare_upload_data()

        if window_duration < 1:
            return

        # Try uploading across 5 attempts
        for attempt in range(5):

            status_text = 'Uploading data to cloud...\n'
            if attempt > 0:
                status_text += ' (Attempt {} of 5)'.format(attempt + 1)
                self._update_ui_status(status_text)

            utils.log('[UPLOAD]', status_text)

            # Upload data via POST
            response = requests.post(url, json=post_data).text
            
            try:
                utils.log("logging response.")
                utils.log('[UPLOAD] Post data to server: ', post_data) # Uncomment this in debug
                utils.log('\n[UPLOAD] Gets back server response:', response)
                response_dict = json.loads(response)

                # Decide what client should do based on server's command
                try:
                    client_action = response_dict['client_action']
                except KeyError:
                    pass
                else:
                    if client_action == 'quit' and not self._host_state.raspberry_pi_mode:
                        utils.log('[UPLOAD] Server wants me to quit.')
                        with self._host_state.lock:
                            self._host_state.quit = True
                    elif client_action == 'start_fast_arp_discovery':
                        utils.log('[UPLOAD] Server wants me to do fast ARP scan.')
                        with self._host_state.lock:
                            self._host_state.fast_arp_scan = True

                # Quit upon UI inactivity
                try:
                    ui_last_active_ts = response_dict['ui_last_active_ts']
                except KeyError:
                    ui_last_active_ts = 0
                if ui_last_active_ts > 0:
                    ui_inactivity_time = int(time.time() - ui_last_active_ts)
                    if ui_inactivity_time > 120 and not self._host_state.raspberry_pi_mode:
                        utils.log('[UPLOAD] About to quit, due to 120 seconds of UI inactivity.')
                        with self._host_state.lock:
                            self._host_state.quit = True

                if response_dict['status'] == 'success':
                    # Update whitelist based on server's response
                    with self._host_state.lock:
                        self._host_state.device_whitelist = \
                            response_dict['inspected_devices']
                        break
                
            except Exception:
                utils.log('[UPLOAD] Failed. Retrying:', traceback.format_exc())
            time.sleep((attempt + 1) ** 2)

        # Report stats to UI
        with self._host_state.lock:
            byte_count = self._host_state.byte_count
            self._host_state.byte_count = 0

        self._update_ui_status(
            'Currently analyzing ' +
            '{:,}'.format(int(byte_count * 8.0 / 1000.0 / window_duration)) +
            ' Kbps of traffic'
        )

        utils.log(
            '[UPLOAD] Total bytes in past epoch:',
            byte_count
        )

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
