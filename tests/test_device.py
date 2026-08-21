#

import random
import string

from chemotion_api import Instance
def random_char(y):
    return ''.join(random.choice(string.ascii_letters) for x in range(y))


def test_upload_file(config_login):
    pass
    #instance = Instance(config_login.get('ELN_URL')).test_connection()
    #jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJmaXJzdF9uYW1lIjoiVGVzdCBEZXZpY2UgMSIsInVzZXJfaWQiOjUsImxhc3RfbmFtZSI6IlQuRCIsImV4cCI6MTcyMzc5ODI4OH0.0nU0qDWaHC7YVl8si8_fzHOJKz5wML97Tcw_7KGaUH8'
    #instance.login_token(jwt)
    #instance.get_user().upload_file('test_config/sample_files/20200702_dcm_PH884_100_red2.DTA')
    #instance.get_user().upload_file('test_config/sample_files/EF-R205.2__GC-BID_inc-5min-30_GC-3min-40-7min-180-2min_Calibrated_11142023_1210_002.gcd.txt')
