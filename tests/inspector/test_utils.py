from src.inspector.utils import _SafeRunError, deserialize_data



class TestSafeRunError:

    def test_implicitly_false(self):
        assert not _SafeRunError()


def test_deserialize_data():
    data = {
        'client_status_text': 'Continuously analyzing your network.\n',
        'dns_dict': '{}',
        'syn_scan_dict': '{}',
        'flow_dict': '{}',
        'device_dict': '{"te8d1920jq3": ["192.168.0.2", "9a9482"], "k123099ai8k": ["192.168.0.3", "aa44a5"]}',
        'ua_dict': '{}',
        'dhcp_dict': '{}',
        'resolver_dict': '{}',
        'client_version': '1.0.3',
        'tls_dict_list': '[]',
        'netdisco_dict': '{}',
        'duration': '5.054013967514038',
        'client_ts': '1647747064'
    }

    ddata = deserialize_data(data)
    assert ddata['duration'] == '5.054013967514038'
    assert len(ddata['device_dict']) == 2
