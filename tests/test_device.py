#

import random
import string

from chemotion_api import Instance
def random_char(y):
    return ''.join(random.choice(string.ascii_letters) for x in range(y))


def test_upload_file(config_login):
    instance = Instance(config_login.get('ELN_URL')).test_connection()
    jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJmaXJzdF9uYW1lIjoiTVMiLCJ1c2VyX2lkIjo1LCJsYXN0X25hbWUiOiJEZXZpY2UiLCJleHAiOjE3MTE2MTA4MTd9.kUTGYC7LodaX2tOjWj3kwxb573WDonzOCLjes-g-ACg'
    instance.login_token(jwt)
    instance.get_user().upload_file('/home/martin/Desktop/tmp/dlw/MSU-02 TestMultiDIE_2023.05.15_17.33.02.result')
    instance.get_user().upload_file('/home/martin/Pictures/Screenshots/MSU-test.img.png')
