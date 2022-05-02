"""
Misc functions.

"""

import datetime
import hashlib
import json
import logging
import logging.config
import netaddr
import netifaces
import os
import re
import requests
import scapy.all as sc
import socket
import sys
import threading
import time
import traceback
import typing as _t
import uuid
import webbrowser

from . import server_config
from pathlib import Path

DEFAULT_LOGGER_NAME = "iot_inspector"
IPv4_REGEX = re.compile(r'[0-9]{0,3}\.[0-9]{0,3}\.[0-9]{0,3}\.[0-9]{0,3}')

sc.conf.verb = 0

# If non empty, then only devices with the following MAC addresses with be
# inspected. Do not populate this list in production. For internal testing.
TEST_OUI_LIST = [
    # 'd83134',  # Roku
    # '74f61c',  # Danny's Pixel phone
]

# Make sure Inspector's directory exits
home_dir = os.path.join(os.path.expanduser('~'), 'princeton-iot-inspector')
if not os.path.isdir(home_dir):
    os.mkdir(home_dir)


def is_ipv4_addr(value):

    return IPv4_REGEX.match(value)


def get_user_config():
    """Returns the user_config dict."""

    user_config_file = os.path.join(os.path.expanduser('~'), 'princeton-iot-inspector', 'iot_inspector_config.json')
    db_file = os.path.join(os.path.expanduser('~'), 'princeton-iot-inspector', 'inspector.db')

    if os.path.exists(user_config_file):
        with open(user_config_file) as fp:
            return json.load(fp)

    resp = requests.get(server_config.NEW_USER_URL)
    content = resp.text.strip()

    # Make sure we're not getting server's error messages
    if resp.status_code != 200:
        raise RuntimeError(
            f"{server_config.NEW_USER_URL} returned code {resp.status_code}: {content!r}"
        )

    user_key = content
    user_key = user_key.replace('-', '')
    secret_salt = str(uuid.uuid4())

    with open(user_config_file, 'w') as fp:
        config_dict = {
            'user_key': user_key,
            'secret_salt': secret_salt,
            'db_file': db_file,
            'partner_interval': 5,
        }
        json.dump(config_dict, fp)

    return config_dict


class TimeoutError(Exception):
    pass


_lock = threading.Lock()

def logger(sublogger: _t.Optional[str] = None) -> logging.Logger:
    """Retrieve the default logger."""

    if sublogger is None:
        logger_name = DEFAULT_LOGGER_NAME
    else:
        logger_name = ".".join((DEFAULT_LOGGER_NAME, sublogger))

    return logging.getLogger(logger_name)


def configure_logging(
    loglevel: int = logging.INFO,
    file_loglevel: _t.Optional[int] = None,
) -> None:
    """Set up the default logging configuration."""

    logfile = Path.home() / "princeton-iot-inspector" / "iot_inspector_logs.txt"
    file_loglevel = loglevel if file_loglevel is None else file_loglevel

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "standard": {
                "format": "[%(asctime)s] (%(levelname)s) %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "stream": {
                "level": loglevel,
                "formatter": "standard",
                "class": "logging.StreamHandler",
            },
            "logfile": {
                "level": file_loglevel,
                "formatter": "standard",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(logfile),
                "maxBytes": 1_000_000,
                "backupCount": 3,
            },
        },
        "loggers": {
            "": {
                "handlers": ["stream"],
                "level": "WARNING",
                "propagate": True,
            },
            DEFAULT_LOGGER_NAME: {
                "handlers": ["stream", "logfile"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    })


def log(*args, level: int = logging.DEBUG):
    logger().log(level, " ".join(map(str, args)))


def get_gateway_ip(timeout=10):
    """Returns the IP address of the gateway."""

    return get_default_route(timeout)[0]


def get_host_ip(timeout=10):
    """Returns the host's local IP (where IoT Inspector client runs)."""

    return get_default_route(timeout)[2]


def _get_routes():

    while True:

        sc.conf.route.resync()
        routes = sc.conf.route.routes
        if routes:
            return routes

        time.sleep(1)


def get_default_route():
    """Returns (gateway_ip, iface, host_ip)."""
    # Discover the active/preferred network interface
    # by connecting to Google's public DNS server
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            iface_ip = s.getsockname()[0]
    except socket.error:
        sys.stderr.write('IoT Inspector cannot run without network connectivity.\n')
        sys.exit(1)

    while True:
        routes = _get_routes()
        default_route = None
        for route in routes:
            if route[4] == iface_ip:
                # Reassign scapy's default interface to the one we selected
                sc.conf.iface = route[3]
                default_route = route[2:5]
                break
        if default_route:
            break

        log('get_default_route: retrying')
        time.sleep(1)

    # If we are using windows, conf.route.routes table doesn't update.
    # We have to update routing table manually for packets
    # to pick the correct route.
    if sys.platform.startswith('win'):
        for i, route in enumerate(routes):
            # if we see our selected iface, update the metrics to 0
            if route[3] == default_route[1]:
                routes[i] = (*route[:-1], 0)

    return default_route


def get_network_ip_range_windows():
    default_iface = get_default_route()
    iface_filter = default_iface[1]

    ip_set = set()
    iface_ip = iface_filter.ip
    iface_guid = iface_filter.guid
    for k, v in netifaces.ifaddresses(iface_guid).items():
        if v[0]['addr'] == iface_ip:
            netmask = v[0]['netmask']
            break

    network = netaddr.IPAddress(iface_ip)
    cidr = netaddr.IPAddress(netmask).netmask_bits()
    subnet = netaddr.IPNetwork('{}/{}'.format(network, cidr))

    return ip_set


def check_ethernet_network():
    """
        Check presence of non-Ethernet network adapters (e.g., VPN).
        VPNs use TUN interfaces which don't have a hardware address.
    """
    default_iface = get_default_route()

    assert default_iface[1] == sc.conf.iface, "incorrect sc.conf.iface"
    iface_str = ''
    if sys.platform.startswith('win'):
        iface_info = sc.conf.iface
        iface_str = iface_info.guid
    else:
        iface_str = sc.conf.iface

    ifaddresses = netifaces.ifaddresses(str(iface_str))
    try:
        iface_mac = ifaddresses[netifaces.AF_LINK][0]['addr']
    except KeyError:
        return False
    return iface_mac != ''


def get_network_ip_range():
    """
        Gets network IP range for the default interface.
    """
    ip_set = set()
    default_route = get_default_route()

    assert default_route[1] == sc.conf.iface, "incorrect sc.conf.iface"

    iface_str = ''
    if sys.platform.startswith('win'):
        iface_info = sc.conf.iface
        iface_str = iface_info.guid
    else:
        iface_str = sc.conf.iface

    netmask = None
    for k, v in netifaces.ifaddresses(str(iface_str)).items():
        if v[0]['addr'] == default_route[2]:
            netmask = v[0]['netmask']
            break

    if netmask is None:
        return set()

    gateway_ip = netaddr.IPAddress(default_route[0])
    cidr = netaddr.IPAddress(netmask).netmask_bits()
    subnet = netaddr.IPNetwork('{}/{}'.format(gateway_ip, cidr))

    for ip in subnet:
        ip_set.add(str(ip))

    return ip_set


def get_my_mac():
    """Returns the MAC addr of the default route interface."""

    mac_set = get_my_mac_set(iface_filter=get_default_route()[1])
    return mac_set.pop()


def get_my_mac_set(iface_filter=None):
    """Returns a set of MAC addresses of the current host."""

    out_set = set()
    if sys.platform.startswith("win"):
        from scapy.arch.windows import NetworkInterface
        if type(iface_filter) == NetworkInterface:
            out_set.add(iface_filter.mac)

    for iface in sc.get_if_list():
        if iface_filter is not None and iface != iface_filter:
            continue
        try:
            mac = sc.get_if_hwaddr(iface)
        except Exception as e:
            continue
        else:
            out_set.add(mac)

    return out_set


class _SafeRunError(object):
    """Used privately to denote error state in safe_run()."""

    def __init__(self):
        pass

    def __bool__(self):
        return False


def restart_upon_crash(func, args=[], kwargs={}):
    """Restarts func upon unexpected exception and logs stack trace."""

    while True:

        result = safe_run(func, args, kwargs)

        if isinstance(result, _SafeRunError):
            time.sleep(1)
            continue

        return result


def safe_run(func, args=[], kwargs={}):
    """Returns _SafeRunError() upon failure and logs stack trace."""

    try:
        return func(*args, **kwargs)

    except Exception as e:

        err_msg = '=' * 80 + '\n'
        err_msg += 'Time: %s\n' % datetime.datetime.today()
        err_msg += 'Function: %s %s %s\n' % (func, args, kwargs)
        err_msg += 'Exception: %s\n' % e
        err_msg += str(traceback.format_exc()) + '\n\n\n'

        with _lock:
            sys.stderr.write(err_msg + '\n')
            log(err_msg)

        return _SafeRunError()


def get_device_id(device_mac, host_state):

    device_mac = str(device_mac).lower().replace(':', '')
    s = device_mac + str(host_state.secret_salt)

    return 's' + hashlib.sha256(s.encode('utf-8')).hexdigest()[0:10]


def smart_max(v1, v2):
    """
        Returns max value even if one value is None.

        Python cannot compare None and int, so build a wrapper
        around it.
    """
    if v1 is None:
        return v2

    if v2 is None:
        return v1

    return max(v1, v2)


def smart_min(v1, v2):
    """
    Returns min value even if one of the value is None.

    By default min(None, x) == None per Python default behavior.

    """

    if v1 is None:
        return v2

    if v2 is None:
        return v1

    return min(v1, v2)


def get_min_max_tuple(min_max_tuple, value):
    """
    Returns a new min_max_tuple with value considered.

    For example:

        min_max_tuple = (2, 3)
        print get_min_max_tuple(min_max_tuple, 4)

    We get back (2, 4).

    """
    min_v, max_v = min_max_tuple

    min_v = smart_min(min_v, value)
    max_v = smart_max(max_v, value)

    return (min_v, max_v)


def get_oui(mac):

    return mac.replace(':', '').lower()[0:6]


def get_os():
    """Returns 'mac', 'linux', or 'windows'. Raises RuntimeError otherwise."""

    os_platform = sys.platform

    if os_platform.startswith('darwin'):
        return 'mac'

    if os_platform.startswith('linux'):
        return 'linux'

    if os_platform.startswith('win'):
        return 'windows'

    raise RuntimeError('Unsupported operating system.')


def open_browser(url):
    try:
        try:
            webbrowser.get('chrome').open(url, new=2)
        except webbrowser.Error:
            webbrowser.open(url, new=2)
    except Exception:
        pass


def deserialize_data(data: dict):
    d = {k: json.loads(v) for k, v in data.items() if k.endswith('dict')}
    for k in data.keys():
        if not k.endswith('dict'):
            d[k] = data[k]

    return d


def test():
    # check_ethernet_network()
    print(get_default_route())


if __name__ == '__main__':
    test()
