"""
Cointrol development settings that extend the defaults ones.

"""
import os

from .settings_defaults import *


DEBUG = True
SECRET_KEY = 'asdf*&*JIOndsfHKhljdsaf778'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'cointrol.sqlite3'),
    }
}


COINTROL_DO_TRADE = False
