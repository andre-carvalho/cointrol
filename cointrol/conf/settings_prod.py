"""
Cointrol production settings that extend the defaults ones.

"""
import os

from .settings_defaults import *


DEBUG = False
SECRET_KEY = 'asdf*&*JIOndsfHKhljdsaf778'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'cointrol.sqlite3'),
    }
}
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # Taken from django/utils/log.py:31
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'mail_admins': {
            'level': 'WARNING',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'stdout': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG'
        }
    },

    'loggers': {
        'cointrol.trader': {
            'handlers': ['stdout', 'mail_admins'],
            'level': 'INFO',
            'propagate': True,
        }
    }
}

COINTROL_DO_TRADE = True
