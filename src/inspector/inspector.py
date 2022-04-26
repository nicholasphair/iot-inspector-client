"""
Entry point for Inspector UI.

"""
import logging
import subprocess
import sys
import sqlite3
from queue import Queue

from . import server_config
from . import utils
from .arp_scan import ArpScan
from .arp_spoof import ArpSpoof
from .data_upload import DataUploader
from .db_dumper import DBDumper
from .fingerprinter import Fingerprinter
from .host_state import HostState
from .netdisco_wrapper import NetdiscoWrapper
from .packet_capture import PacketCapture
from .packet_processor import PacketProcessor
from .syn_scan import SynScan


WINDOWS_STARTUP_TEXT = """

======================================
Princeton IoT Inspector for Windows 10
======================================

Running on IP Address: {0}

We have also opened a new browser window for you to view the IoT Inspector report. If you don't see a new browser window, use the following private link:

{1}/user/{2}

To stop IoT Inspector, simply close this window or hit Control + C.

Questions? Email us at iot-inspector@lists.cs.princeton.edu.

"""


def start():
    """
    Initializes inspector by spawning a number of background threads.
    
    Returns the host state once all background threats are started.
    
    """
    # Read from home directory the user_key. If non-existent, get one from
    # cloud.
    config_dict = utils.get_user_config()

    utils.log('[MAIN] Starting.')

    gateway_ip, iface, host_ip = utils.get_default_route()
    utils.log('Running Inspector on IP Address: {}\n \
    Running Inspector on Network Interface: {}'.format(host_ip, iface))

    # Set up environment
    state = HostState()
    state.user_key = config_dict['user_key'].replace('-', '')
    state.secret_salt = config_dict['secret_salt']
    state.host_mac = utils.get_my_mac()
    state.gateway_ip, _, state.host_ip = utils.get_default_route()

    # Read special command-line arguments
    if '--raspberry_pi_mode' in sys.argv:
        state.raspberry_pi_mode = True

    assert utils.is_ipv4_addr(state.gateway_ip)
    assert utils.is_ipv4_addr(state.host_ip)

    state.packet_processor = PacketProcessor(state)

    utils.log('Initialized:', state.__dict__)

    # Continously discover devices
    arp_scan_thread = ArpScan(state)
    arp_scan_thread.start()

    # Continously discover ports via SYN scans
    syn_scan_thread = SynScan(state)
    syn_scan_thread.start()

    # Continuously gather SSDP data
    netdisco_thread = NetdiscoWrapper(state)
    netdisco_thread.start()

    # Continuously capture packets
    packet_capture_thread = PacketCapture(state)
    packet_capture_thread.start()

    # Continously spoof ARP
    if '--no_spoofing' not in sys.argv:
        arp_spoof_thread = ArpSpoof(state)
        arp_spoof_thread.start()

    # Continuously upload data
    to_db_queue = Queue()
    data_upload_thread = DataUploader(state, to_db_queue)
    data_upload_thread.start()

    # Write data to db.
    db_name = config_dict['db_file']
    db_dump_thread = DBDumper(db_name, to_db_queue)
    db_dump_thread.start()

    # Fingerprint the data.
    fp_thread = Fingerprinter(state, db_name)
    fp_thread.start()


    # Suppress scapy warnings
    try:
        logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
    except Exception:
        pass

    # Suppress flask messages
    try:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    except Exception:
        pass

    # Insert a dash every four characters to make user-key easier to type
    pretty_user_key = ''
    for (ix, char) in enumerate(state.user_key):
        if (ix > 0) and (ix % 4 == 0):
            pretty_user_key += '-'
        pretty_user_key += char

    print('\n' * 100)

    os_platform = utils.get_os()    

    print(WINDOWS_STARTUP_TEXT.format(host_ip, server_config.BASE_URL, pretty_user_key))

    # Open a Chrome window that runs IoT Inspector since running IoT Inspector
    # on Chrome is preferred. Note that a new webpage will be opened 
    # in non-privileged mode. 

    # For users that do not use chrome, the default browser will be opened in 
    # Windows 10, and Safari will be opened in macOS.

    if os_platform == 'windows' or 'mac':
        url = '{0}/user/{1}'.format(server_config.BASE_URL, pretty_user_key)
        utils.open_browser(url)
    return state


def enable_ip_forwarding():

    os_platform = utils.get_os()

    if os_platform == 'mac':
        cmd = ['/usr/sbin/sysctl', '-w', 'net.inet.ip.forwarding=1']
    elif os_platform == 'linux':
        cmd = ['sysctl', '-w', 'net.ipv4.ip_forward=1']
    elif os_platform == 'windows':
        cmd = ['powershell', 'Set-NetIPInterface', '-Forwarding', 'Enabled']

    assert subprocess.call(cmd) == 0


def disable_ip_forwarding():

    os_platform = utils.get_os()

    if os_platform == 'mac':
        cmd = ['/usr/sbin/sysctl', '-w', 'net.inet.ip.forwarding=0']
    elif os_platform == 'linux':
        cmd = ['sysctl', '-w', 'net.ipv4.ip_forward=0']
    elif os_platform == 'windows':
        cmd = ['powershell', 'Set-NetIPInterface', '-Forwarding', 'Disabled']

    assert subprocess.call(cmd) == 0
