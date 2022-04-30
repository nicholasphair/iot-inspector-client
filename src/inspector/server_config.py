import sys


BASE_URL = 'http://localhost:8080'

NEW_USER_URL = BASE_URL + '/generate_user_key'

PARTNER_URL = BASE_URL + '/partner'

MODEL_URL = BASE_URL + '/model'

SEPARATE = BASE_URL + '/separate'

HEARTBEAT = BASE_URL + '/heartbeat'

SUBMIT_URL = BASE_URL + '/submit_data/{user_key}'

FINGERPRINT_URL = BASE_URL + '/submit_fingerprint/{user_key}'

UTC_OFFSET_URL = BASE_URL + '/submit_utc_offset/{user_key}/{offset_seconds}'

CHECK_CONSENT_URL = BASE_URL + '/has_signed_consent_form/{user_key}'

INIT_URL = BASE_URL + '/setup?started_from_app=yes'

NPCAP_ERROR_URL = 'https://iotinspector.org/npcap-error/'

NETMASK_ERROR_URL = 'https://iotinspector.org/netmask-error/'
